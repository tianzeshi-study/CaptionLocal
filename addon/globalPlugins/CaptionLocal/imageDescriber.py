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

import wx
import config
from logHandler import log
import ui
import api

from .captioner import ImageCaptioner
from .captioner import imageCaptionerFactory

try:
	import addonHandler
	addonHandler.initTranslation()
except:
	pass

def _screenshotNavigator() -> bytes:
	"""Capture a screenshot of the current navigator object.

	:Return: The captured image data as bytes in JPEG format.
	"""
	# Get the currently focused object on screen
	obj = api.getNavigatorObject()

	# Get the object's position and size information
	x, y, width, height = obj.location

	# Create a bitmap with the same size as the object
	bmp = wx.Bitmap(width, height)

	# Create a memory device context for drawing operations on the bitmap
	mem = wx.MemoryDC(bmp)

	# Copy the specified screen region to the memory bitmap
	mem.Blit(0, 0, width, height, wx.ScreenDC(), x, y)

	# Convert the bitmap to an image object for more flexible operations
	image = bmp.ConvertToImage()

	# Create a byte stream object to save image data as binary data
	body = io.BytesIO()

	# Save the image to the byte stream in JPEG format
	image.SaveFile(body, wx.BITMAP_TYPE_JPEG)

	# Read the binary image data from the byte stream
	imageData = body.getvalue()
	return imageData


def _messageCaption(captioner: ImageCaptioner, imageData: bytes) -> None:
	"""Generate a caption for the given image data.

	:param captioner: The captioner instance to use for generation.
	:param imageData: The image data to caption.
	"""
	try:
		description = captioner.generateCaption(image=imageData)
	except Exception:
		# Translators: error message when an image description cannot be generated
		wx.CallAfter(ui.message, _("Failed to generate description"))
		log.exception("Failed to generate caption")
	else:
		wx.CallAfter(
			ui.message,
			# Translators: Presented when an AI image description has been generated.
			# {description} will be replaced with the generated image description.
			_("Could be: {description}").format(description=description),
		)
		api.copyToClip(text=description, notify=False)


class ImageDescriber:
	"""module for local image caption functionality.

	This module provides image captioning using local ONNX models.
	It can capture screen regions and generate descriptive captions.
	"""

	def __init__(self) -> None:
		self.isModelLoaded = False
		self.captioner: ImageCaptioner | None = None
		self.captionThread: Thread | None = None
		self.loadModelThread: Thread | None = None

		enable = config.conf["captionLocal"]["loadModelWhenInit"]
		# Load model when initializing
		if enable:
			self.loadModelInBackground()

	def terminate(self):
		for t in [self.captionThread, self.loadModelThread]:
			if t is not None and t.is_alive():
				# We can't really join here if we are on the main thread and it might block
				# but for an addon terminate it should be fine if it's not too long
				pass
		self.captioner = None

	def runCaption(self, gesture=None) -> None:
		"""Script to run image captioning on the current navigator object.

		:param gesture: The input gesture that triggered this script.
		"""
		self._doCaption()

	def _doCaption(self) -> None:
		"""Real logic to run image captioning on the current navigator object."""
		imageData = _screenshotNavigator()

		if not self.isModelLoaded:
			# In the addon, we might want to just load it or show a message
			ui.message(_("loading model..."))
			self._loadModel()
			if not self.isModelLoaded:
				return

		if self.captionThread is not None and self.captionThread.is_alive():
			return

		self.captionThread = threading.Thread(
			target=_messageCaption,
			args=(self.captioner, imageData),
			name="RunCaptionThread",
		)
		# Translators: Message when starting image recognition
		ui.message(_("getting image description..."))
		self.captionThread.start()

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
			# In the addon, we can use the ModelManager to download
			ui.message(_("Model not found. Please use Model Manager to download."))
		except Exception:
			self.isModelLoaded = False
			# Translators: error message when fail to load model
			wx.CallAfter(ui.message, _("failed to load image captioner"))
			log.exception("Failed to load image captioner model")
		else:
			self.isModelLoaded = True
			# Translators: Message when successfully load the model
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
			# Translators: Message when image captioning terminates
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
