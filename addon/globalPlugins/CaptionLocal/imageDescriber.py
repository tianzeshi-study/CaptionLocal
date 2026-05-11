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
import threading
from threading import Thread
import os
import ctypes

import wx
import config
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
			
			# Copy to clipboard at the end
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

	def _loadModel(self, localModelDirPath: str | None = None) -> None:
		"""Load the ONNX model for image captioning.

		:param localModelDirPath: path of model directory
		"""

		if not localModelDirPath:
			modelsDir = config.conf["captionLocal"]["modelsDir"]
			currentModel = config.conf["captionLocal"]["currentModel"]
			localModelDirPath = os.path.join(modelsDir, currentModel)
		
		encoderPath = os.path.join(localModelDirPath, "onnx", "encoder_model_quantized.onnx")
		decoderPath = os.path.join(localModelDirPath, "onnx", "decoder_model_merged_quantized.onnx")
		configPath = os.path.join(localModelDirPath, "config.json")

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
			ui.message(_("Model not found. Please use Model Manager to download."))
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
