# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2025 NV Access Limited, Tianze
# This file may be used under the terms of the GNU General Public License, version 2 or later, as modified by the NVDA license.
# For full terms and any additional permissions, see the NVDA license file: https://github.com/nvaccess/nvda/blob/master/copying.txt

"""ImageDescriber module for NVDA.

This module provides local image captioning functionality using ONNX models.
It allows users to capture screen regions and generate captions using local AI models.
"""

import io
import json
import time
import threading
from threading import Thread
import os
import ctypes
from typing import Callable, Dict

ProgressCallback = Callable[[str, int, int, float], None]

import gui
import wx
import config
from gui.message import MessageDialog, DefaultButton, ReturnCode, DialogType
from logHandler import log
import ui
import api
import queueHandler

from contentRecog import ContentRecognizer, SimpleTextResult, RecogImageInfo
from .captioner import ImageCaptioner
from .captioner import imageCaptionerFactory

try:
	import addonHandler
	addonHandler.initTranslation()
except:
	pass


class ImageDescDownloader:
	"""Helper class to manage model downloads with progress dialog,
	matching the pattern in gui_localCaptioner.
	"""
	_downloadThread: Thread | None = None

	def __init__(self, modelId: str, filesToDownload: list, resolvePath: str, completionCallback: Callable):
		self.modelId = modelId
		self.filesToDownload = filesToDownload
		self.resolvePath = resolvePath
		self.completionCallback = completionCallback
		self.downloadDict: Dict[str, tuple[int, int]] = {}
		self.modelDownloader: 'ModelDownloader' | None = None
		self._shouldCancel = False
		self._progressDialog: wx.ProgressDialog | None = None

	def onDownload(self, progressCallback: ProgressCallback) -> None:
		from .modelDownloader import ModelDownloader
		self.modelDownloader = ModelDownloader()
		import config
		baseModelsDir = config.conf["captionLocal"]["modelsDir"]
		(success, fail) = self.modelDownloader.downloadModelsMultithreaded(
			modelsDir=baseModelsDir,
			modelName=self.modelId,
			filesToDownload=self.filesToDownload,
			resolvePath=self.resolvePath,
			progressCallback=progressCallback,
		)
		if len(fail) == 0:
			wx.CallAfter(self.openSuccessDialog)
		else:
			wx.CallAfter(self.openFailDialog)

	def openSuccessDialog(self) -> None:
		confirmationButton = (DefaultButton.OK.value._replace(defaultFocus=True, fallbackAction=True),)
		self._stopped()
		
		dialog = MessageDialog(
			parent=None,
			title=_("Download successful"),
			message=_("Model {modelId} installed successfully.").format(modelId=self.modelId),
			dialogType=DialogType.STANDARD,
			buttons=confirmationButton,
		)

		if dialog.ShowModal() == ReturnCode.OK:
			if self.completionCallback:
				self.completionCallback(True)

	def openFailDialog(self) -> None:
		if self._shouldCancel:
			return

		confirmationButtons = (
			DefaultButton.YES.value._replace(defaultFocus=True, fallbackAction=False),
			DefaultButton.NO.value._replace(defaultFocus=False, fallbackAction=True),
		)

		dialog = MessageDialog(
			parent=None,
			title=_("Download failed"),
			message=_("Model download failed. Would you like to retry?"),
			dialogType=DialogType.WARNING,
			buttons=confirmationButtons,
		)

		if dialog.ShowModal() == ReturnCode.YES:
			self.doDownload()
		else:
			self._stopped()
			if self.completionCallback:
				self.completionCallback(False)

	def openDownloadDialog(self) -> None:
		if ImageDescDownloader._downloadThread is not None and ImageDescDownloader._downloadThread.is_alive():
			ui.message(_("image captioning is still downloading, please wait..."))
			return
		
		confirmationButtons = (
			DefaultButton.YES.value._replace(defaultFocus=True, fallbackAction=False),
			DefaultButton.NO.value._replace(defaultFocus=False, fallbackAction=True),
		)

		dialog = MessageDialog(
			parent=None,
			title=_("Confirm download"),
			message=_("Model {modelId} not installed. Would you like to install?").format(modelId=self.modelId),
			dialogType=DialogType.WARNING,
			buttons=confirmationButtons,
		)

		if dialog.ShowModal() == ReturnCode.YES:
			gui.mainFrame.prePopup()
			self._progressDialog = wx.ProgressDialog(
				_("Downloading Model"),
				_("Connecting"),
				style=wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_AUTO_HIDE,
				parent=gui.mainFrame,
			)
			self.doDownload()

	def _updateProgress(self, progress: int, message: str):
		if getattr(self, "_isUpdatingProgress", False) or not self._progressDialog:
			return
		self._isUpdatingProgress = True
		try:
			capped = min(max(int(progress), 0), 99)
			cont, skip = self._progressDialog.Update(capped, message)
			if not cont:
				self._shouldCancel = True
				self._stopped()
		except Exception:
			pass
		finally:
			self._isUpdatingProgress = False

	def doDownload(self):
		def progressCallback(
			fileName: str,
			downloadedBytes: int,
			totalBytes: int,
			_percentage: float,
		) -> None:
			self.downloadDict[fileName] = (downloadedBytes, totalBytes)
			downloadedSum = sum(d for d, _ in self.downloadDict.values())
			totalSum = sum(t for _, t in self.downloadDict.values())
			ratio = downloadedSum / totalSum if totalSum > 0 else 0.0
			totalProgress = int(ratio * 100)

			# UPDATE PROGRESS ONLY WHEN ALL FILES ARE TRACKED
			# This matches reference and fixes the early 100% bug
			if len(self.downloadDict) == len(self.filesToDownload):
				if self._progressDialog and not self._shouldCancel:
					wx.CallAfter(self._updateProgress, totalProgress, _("Downloading..."))

		ImageDescDownloader._downloadThread = threading.Thread(
			target=self.onDownload,
			name="ModelDownloadThread",
			daemon=False,
			args=(progressCallback,),
		)
		ImageDescDownloader._downloadThread.start()

	def _stopped(self):
		if self.modelDownloader:
			self.modelDownloader.requestCancel()
		ImageDescDownloader._downloadThread = None
		if self._progressDialog:
			self._progressDialog.Hide()
			self._progressDialog.Destroy()
			self._progressDialog = None
			wx.CallLater(50, gui.mainFrame.postPopup)


class DependencyDownloader:
	"""Downloads runtime dependencies with progress dialog."""

	def __init__(self, missing_runtimes, dm, localModelDirPath, completionCallback):
		self.missing_runtimes = missing_runtimes
		self.dm = dm
		self.localModelDirPath = localModelDirPath
		self.completionCallback = completionCallback
		self._shouldCancel = False
		self._progressDialog: wx.ProgressDialog | None = None
		self._isUpdatingProgress = False
		self._downloadThread: Thread | None = None

	def openDownloadDialog(self):
		confirmationButtons = (
			DefaultButton.YES.value._replace(defaultFocus=True, fallbackAction=False),
			DefaultButton.NO.value._replace(defaultFocus=False, fallbackAction=True),
		)

		dialog = MessageDialog(
			parent=None,
			title=_("Download Dependencies"),
			message=_("This model requires additional components (runtimes). Would you like to download them now?"),
			dialogType=DialogType.WARNING,
			buttons=confirmationButtons,
		)

		if dialog.ShowModal() == ReturnCode.YES:
			gui.mainFrame.prePopup()
			self._progressDialog = wx.ProgressDialog(
				_("Downloading Dependencies"),
				_("Preparing..."),
				maximum=100,
				parent=gui.mainFrame,
				style=wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_AUTO_HIDE
			)
			self._shouldCancel = False
			self.doDownload()
		else:
			ui.message(_("Model cannot be loaded without dependencies."))

	def _updateProgress(self, progress: int, message: str):
		if self._isUpdatingProgress or not self._progressDialog:
			return
		self._isUpdatingProgress = True
		try:
			capped = min(max(int(progress), 0), 99)
			cont, skip = self._progressDialog.Update(capped, message)
			if not cont:
				self._shouldCancel = True
		except Exception:
			pass
		finally:
			self._isUpdatingProgress = False

	def doDownload(self):
		def download_worker():
			try:
				for runtime_id in self.missing_runtimes:
					if self._shouldCancel:
						break

					def cb(file, down, total, pct):
						if self._progressDialog and not self._shouldCancel:
							if file.startswith("[EXTRACTING]"):
								clean_name = file.replace("[EXTRACTING]", "")
								msg = _("Extracting and installing {file}...").format(file=clean_name)
							elif pct >= 100:
								msg = _("Extracting {file}...").format(file=file)
							else:
								msg = _("Downloading {file}... ({pct}%)").format(file=file, pct=int(pct))
							wx.CallAfter(self._updateProgress, int(pct), msg)

					if not self.dm.downloadAndInstall(runtime_id, progress_callback=cb):
						raise Exception(f"Failed to install {runtime_id}")

				if not self._shouldCancel:
					wx.CallAfter(self._onComplete, True)
				else:
					wx.CallAfter(self._onComplete, False)
			except Exception as e:
				log.exception("Dependency download failed")
				wx.CallAfter(self._onComplete, False, str(e))

		self._downloadThread = threading.Thread(
			target=download_worker,
			name="DependencyDownloadThread",
			daemon=False,
		)
		self._downloadThread.start()

	def _onComplete(self, success: bool, error: str | None = None):
		if self._progressDialog:
			self._progressDialog.Hide()
			self._progressDialog.Destroy()
			self._progressDialog = None
			wx.CallLater(50, gui.mainFrame.postPopup)

		if success:
			if self.completionCallback:
				self.completionCallback()
		else:
			if error:
				ui.message(_("Dependency download failed: {error}").format(error=error))
			elif not self._shouldCancel:
				ui.message(_("Dependency download failed."))


class ImageDescriber(ContentRecognizer):
	"""module for local image caption functionality.

	This module provides image captioning using local ONNX models.
	It can capture screen regions and generate descriptive captions.
	"""

	# Translators: Name of the content recognizer
	name = _("Local Image Caption")

	def __init__(self) -> None:
		super().__init__()
		self.isModelLoaded = False
		self.captioner: ImageCaptioner | None = None
		self.captionThread: Thread | None = None
		self.loadModelThread: Thread | None = None
		self._current_text = ""
		self._onResult_callback = None
		
		# For model download tracking
		self._activeDownloader: 'ModelDownloader' | None = None
		self._progressDialog: wx.ProgressDialog | None = None
		self.downloadDict: Dict[str, tuple[int, int]] = {}
		self._shouldCancel = False

		enable = config.conf["captionLocal"]["loadModelWhenInit"]
		# Load model when initializing
		if enable:
			self.loadModelInBackground()

	def terminate(self):
		for t in [self.captionThread, self.loadModelThread]:
			if t is not None and t.is_alive():
				pass
		self.captioner = None

	def getResizeFactor(self, width, height):
		if width < 100 or height < 100:
			return 4
		return 1

	def recognize(self, pixels: ctypes.Array, imageInfo: RecogImageInfo, onResult):
		"""Asynchronously recognize content from an image.
		
		@param pixels: The pixels of the image as a two dimensional array of RGBQUADs.
		@param imageInfo: Information about the image for recognition.
		@param onResult: A callable which takes a RecognitionResult (or an exception on failure).
		"""
		if not self.isModelLoaded:
			# If model is not loaded, we might need to load it.
			# But in contentRecog context, we should probably fail or message.
			ui.message(_("loading model..."))
			self._loadModel()
			if not self.isModelLoaded:
				onResult(Exception(_("Model not loaded")))
				return

		if self.captionThread is not None and self.captionThread.is_alive():
			# Already running? contentRecog usually handles one at a time.
			return

		self._onResult_callback = onResult
		self._current_text = ""

		self.captionThread = threading.Thread(
			target=self._do_recognize,
			args=(pixels, imageInfo),
			name="RunCaptionThread",
		)
		self.captionThread.start()

	def _do_recognize(self, pixels, imageInfo):
		from PIL import Image
		
		width = imageInfo.recogWidth
		height = imageInfo.recogHeight
		
		try:
			# Convert pixels (BGRA8) to Image
			# pixels is ctypes.Array of RGBQUAD (BGRA)
			# PIL "RGBX" handles 4-byte pixels, "BGRX" is what we want for BGRA if we ignore A
			image = Image.frombytes("RGBX", (width, height), pixels, "raw", "BGRX")
			image = image.convert("RGB")
			
			buffer = io.BytesIO()
			image.save(buffer, format="JPEG")
			imageData = buffer.getvalue()

			def on_token(token):
				self._current_text += token
				self._update_result()

			final_caption = self.captioner.generateCaption(
				image=imageData,
				onToken=on_token
			)
			# Final update to ensure UI is shown and text is correct
			if final_caption and not self._current_text:
				self._current_text = final_caption
			self._update_result()
			
			# Copy to clipboard at the end if enabled
			if config.conf['captionLocal'].get('copyToClipboard', False):
				queueHandler.queueFunction(queueHandler.eventQueue, api.copyToClip, text=final_caption, notify=False)

		except Exception as e:
			log.exception("Failed to generate caption")
			if self._onResult_callback:
				self._onResult_callback(e)

	def _update_result(self):
		if not self._onResult_callback:
			return

		result = SimpleTextResult(self._current_text)
		
		# If this is a RefreshableRecogResultNVDAObject, we can use its _onResult for updates
		onResult = self._onResult_callback
		ui_obj = getattr(onResult, "__self__", None)
		
		if ui_obj and hasattr(ui_obj, "result") and ui_obj.result is not None:
			# Subsequent update
			if hasattr(ui_obj, "_onResult"):
				queueHandler.queueFunction(queueHandler.eventQueue, ui_obj._onResult, result)
			else:
				queueHandler.queueFunction(queueHandler.eventQueue, onResult, result)
		elif self._current_text:
			# First result (or not a refreshable object)
			# Only show UI if we have text
			queueHandler.queueFunction(queueHandler.eventQueue, onResult, result)

	def cancel(self):
		"""Cancel the recognition in progress."""
		# For now, we don't have a good way to kill the thread/onnx inference safely.
		self._onResult_callback = None

	def _showDownloadDialog(self, modelId: str, localModelDirPath: str):
		def show_ui():
			confirmationButtons = (
				DefaultButton.YES.value._replace(defaultFocus=True, fallbackAction=False),
				DefaultButton.NO.value._replace(defaultFocus=False, fallbackAction=True),
			)
			
			dialog = MessageDialog(
				parent=None,
				title=_("Confirm download"),
				message=_("Model {modelId} not found. Would you like to download it now?").format(modelId=modelId),
				dialogType=DialogType.WARNING,
				buttons=confirmationButtons,
			)

			if dialog.ShowModal() != ReturnCode.YES:
				return

			# Load model config to get files list
			filesToDownload = []
			resolvePath = "/resolve/main"
			try:
				config_file = os.path.join(os.path.dirname(__file__), "models.json")
				if os.path.exists(config_file):
					with open(config_file, "r", encoding="utf-8") as f:
						data = json.load(f)
						for m in data.get("models", []):
							if m.get("id") == modelId:
								filesToDownload = m.get("files", [])
								resolvePath = m.get("resolvePath", "/resolve/main")
								break
			except Exception:
				log.exception("Failed to load models.json")
			
			if not filesToDownload:
				# Fallback to vit-gpt2 files
				filesToDownload = [
					"onnx/encoder_model_quantized.onnx",
					"onnx/decoder_model_merged_quantized.onnx", 
					"config.json",
					"vocab.json",
					"preprocessor_config.json"
				]

			gui.mainFrame.prePopup()
			self._progressDialog = wx.ProgressDialog(
				_("Downloading Model"),
				_("Connecting"),
				maximum=100,
				parent=gui.mainFrame,
				style=wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_AUTO_HIDE
			)
			
			self.downloadDict = {}
			self._shouldCancel = False
			
			from .modelDownloader import ModelDownloader
			self._activeDownloader = ModelDownloader()

			def download_worker():
				try:
					def cb(fileName, downloaded, total, pct):
						self.downloadDict[fileName] = (downloaded, total)
						# Guard: only update progress when all files have reported their sizes
						if len(self.downloadDict) != len(filesToDownload):
							return
						downloadedSum = sum(d for d, _ in self.downloadDict.values())
						totalSum = sum(t for _, t in self.downloadDict.values())
						ratio = downloadedSum / totalSum if totalSum > 0 else 0.0
						totalProgress = int(ratio * 100)

						if self._progressDialog and not self._shouldCancel:
							msg = _("Downloading... ({pct}%)").format(pct=totalProgress)
							wx.CallAfter(self._updateProgressDialog, totalProgress, msg)

					localModelDirPath_norm = os.path.normpath(localModelDirPath)
					# Our downloader expects modelsDir and modelName separately
					import config
					baseModelsDir = config.conf["captionLocal"]["modelsDir"]

					successful, failed = self._activeDownloader.downloadModelsMultithreaded(
						modelsDir=baseModelsDir,
						modelName=modelId,
						filesToDownload=filesToDownload,
						resolvePath=resolvePath,
						progressCallback=cb
					)

					if not failed and not self._activeDownloader.cancelRequested:
						wx.CallAfter(self._cleanupDownload, True, localModelDirPath_norm)
					else:
						wx.CallAfter(self._cleanupDownload, False, localModelDirPath_norm)
				except Exception as e:
					log.exception("Model download failed")
					wx.CallAfter(self._cleanupDownload, False, localModelDirPath, str(e))

			threading.Thread(target=download_worker, name="ModelDownloadThread", daemon=False).start()

		wx.CallAfter(show_ui)

	def _updateProgressDialog(self, progress: int, message: str):
		if getattr(self, "_isUpdatingProgress", False) or not self._progressDialog:
			return
		self._isUpdatingProgress = True
		try:
			capped = min(max(int(progress), 0), 99)
			cont, skip = self._progressDialog.Update(capped, message)
			if not cont:
				self._shouldCancel = True
				if self._activeDownloader:
					self._activeDownloader.requestCancel()
		except Exception:
			pass
		finally:
			self._isUpdatingProgress = False

	def _cleanupDownload(self, success: bool, localModelDirPath: str, error: str | None = None):
		if self._activeDownloader:
			self._activeDownloader.requestCancel()
			self._activeDownloader = None
		if self._progressDialog:
			self._progressDialog.Hide()
			self._progressDialog.Destroy()
			self._progressDialog = None
			wx.CallLater(50, gui.mainFrame.postPopup)

		if success:
			ui.message(_("Model downloaded successfully."))
			self.loadModelInBackground(localModelDirPath)
		else:
			if error:
				ui.message(_("Model download failed: {error}").format(error=error))
			elif not self._shouldCancel:
				ui.message(_("Model download failed."))

	def _loadModel(self, localModelDirPath: str | None = None) -> None:
		"""Load the ONNX model for image captioning.

		:param localModelDirPath: path of model directory
		"""
		currentModel = config.conf["captionLocal"]["currentModel"]

		if not localModelDirPath:
			modelsDir = config.conf["captionLocal"]["modelsDir"]
			# Ensure modelsDir exists
			if not os.path.exists(modelsDir):
				try:
					os.makedirs(modelsDir, exist_ok=True)
				except Exception:
					log.exception(f"Failed to create models directory: {modelsDir}")
			
			localModelDirPath = os.path.join(modelsDir, currentModel)

		# Special handling for custom/endpoint
		configPath = os.path.join(localModelDirPath, "config.json")
		if currentModel == "custom/endpoint" or (os.path.exists(configPath) and "CustomEndpoint" in open(configPath, "r", encoding="utf-8").read()):
			from . import customEndpointConfig
			if not customEndpointConfig.is_config_valid(configPath):
				def show_ui():
					if wx.CallAfter(customEndpointConfig.show_config_dialog(None, configPath)):
						# Reload after config
						self.loadModelInBackground(localModelDirPath)
					else:
						ui.message(_("Custom endpoint not configured"))
				
				wx.CallAfter(show_ui)
				return
		
		localModelDirPath = os.path.normpath(localModelDirPath)

		# Special handling for custom/endpoint
		configPath = os.path.join(localModelDirPath, "config.json")

		if currentModel != "custom/endpoint" and not os.path.exists(configPath):
			self._showDownloadDialog(currentModel, localModelDirPath)
			return

		if currentModel == "custom/endpoint" or (os.path.exists(configPath) and "CustomEndpoint" in open(configPath, "r", encoding="utf-8").read()):
			from . import customEndpointConfig
			if not customEndpointConfig.is_config_valid(configPath):
				def show_ui():
					if customEndpointConfig.show_config_dialog(None, configPath):
						# Reload after config
						self.loadModelInBackground(localModelDirPath)
					else:
						ui.message(_("Custom endpoint not configured"))
				
				wx.CallAfter(show_ui)
				return

		# Runtime Dependency Check
		from .dependencyManager import DependencyManager
		dm = DependencyManager()
		runtimes = dm.getRequiredRuntimes(currentModel)
		missing = [r for r in runtimes if not dm.isRuntimeInstalled(r)]
		if missing:
			def on_deps_downloaded():
				# Proceed to load the model after dependencies are installed
				self.loadModelInBackground(localModelDirPath)

			downloader = DependencyDownloader(missing, dm, localModelDirPath, on_deps_downloaded)
			wx.CallAfter(downloader.openDownloadDialog)
			return

		encoderPath = os.path.join(localModelDirPath, "onnx", "encoder_model_quantized.onnx")
		decoderPath = os.path.join(localModelDirPath, "onnx", "decoder_model_merged_quantized.onnx")

		try:
			from . import modelConfig
			modelConfig.initialize()
			self.captioner = imageCaptionerFactory(
				encoderPath=encoderPath,
				decoderPath=decoderPath,
				configPath=configPath,
			)
		except FileNotFoundError:
			self.isModelLoaded = False
			self._showDownloadDialog(currentModel, localModelDirPath)
		except Exception:
			self.isModelLoaded = False
			wx.CallAfter(ui.message, _("failed to load image captioner"))
			log.exception("Failed to load image captioner model")
		else:
			self.isModelLoaded = True
			wx.CallAfter(ui.message, _("image captioning on"))

	def loadModelInBackground(self, localModelDirPath: str | None = None) -> None:
		"""load model in child thread

		:param localModelDirPath: path of model directory
		"""
		self.loadModelThread = threading.Thread(
			target=self._loadModel,
			args=(localModelDirPath,),
			name="LoadModelThread",
		)
		self.loadModelThread.start()

	def _doReleaseModel(self) -> None:
		if hasattr(self, "captioner") and self.captioner:
			del self.captioner
			self.captioner = None
			ui.message(_("image captioning off"))
			self.isModelLoaded = False

	def toggleSwitch(self) -> None:
		"""do load/unload the model from memory."""
		if self.isModelLoaded:
			self._doReleaseModel()
		else:
			self.loadModelInBackground()

	def toggleImageCaptioning(self, gesture=None) -> None:
		"""do load/unload the model from memory.

		:param gesture: gesture to toggle this function
		"""
		self.toggleSwitch()
