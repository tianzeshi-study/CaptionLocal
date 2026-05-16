# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2025 NV Access Limited, Tianze
# This file may be used under the terms of the GNU General Public License, version 2 or later, as modified by the NVDA license.
# For full terms and any additional permissions, see the NVDA license file: https://github.com/nvaccess/nvda/blob/master/copying.txt

"""Caption Local Global Plugin for NVDA.

This plugin provides local image captioning functionality using ONNX models.
It allows users to capture screen regions and generate captions using local AI models.
"""

import os
import sys
import threading
from typing import Optional

import wx
import gui
import globalVars
import config
import scriptHandler
import globalPluginHandler
from contentRecog import recogUi

# Add libs directory to path
_here = os.path.dirname(__file__)
_libsDir = os.path.join(_here, "libs")
if os.path.exists(_libsDir) and _libsDir not in sys.path:
	sys.path.insert(0, _libsDir)

from .imageDescriber import ImageDescriber
from .modelManager import ModelManagerFrame
from .panel import CaptionLocalSettingsPanel

try:
	import addonHandler
	addonHandler.initTranslation()
except:
	pass

# Module-level configuration
_here = os.path.dirname(__file__)
_modelsDir = os.path.abspath(os.path.join(_here, "..", "..", "models"))

CONFSPEC = {
	"modelsDir": f"string(default={_modelsDir})",
	"currentModel": "string(default=Xenova/vit-gpt2-image-captioning)",
	"loadModelWhenInit": "boolean(default=true)",
	"copyToClipboard": "boolean(default=false)"
}

config.conf.spec['captionLocal'] = CONFSPEC


def disableInSecureMode(decoratedCls):
	if globalVars.appArgs.secure:
		return globalPluginHandler.GlobalPlugin
	return decoratedCls


@disableInSecureMode
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Global plugin for Caption Local functionality.
	
	This plugin provides image captioning using local ONNX models.
	It can capture screen regions and generate descriptive captions.
	"""

	def __init__(self) -> None:
		"""Initialize the global plugin."""
		super().__init__()
		self.imageDescriber = ImageDescriber()
		self.managerFrame: Optional[ModelManagerFrame] = None
		self.menu = gui.mainFrame.sysTrayIcon.toolsMenu
		self.manager_item = self.menu.Append(wx.ID_ANY, _("Model Manager"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.script_openManager, self.manager_item)

		
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(CaptionLocalSettingsPanel)

	def terminate(self) -> None:
		"""Clean up resources when the plugin is terminated."""
		if self.imageDescriber:
			self.imageDescriber.terminate()
		try:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(CaptionLocalSettingsPanel)
		except (ValueError, AttributeError):
			pass

	@scriptHandler.script(
		# Translators: Description for the image caption script
		description=_("image caption using local model"),
		# Translators: Category of addon in input gestures.
		category=_("Caption Local"),
		gesture="kb:NVDA+windows+,"
	)
	def script_runCaption(self, gesture) -> None:
		"""Script to run image captioning on the current navigator object."""
		recogUi.recognizeNavigatorObject(self.imageDescriber)

	@scriptHandler.script(
		# Translators: Description for the release model script
		description=_("toggle local model"),
		# Translators: Category of addon in input gestures.
		category=_("Caption Local"),
		gesture="kb:NVDA+windows+shift+,"
	)
	def script_toggleModel(self, gesture) -> None:
		"""Script to toggle the loaded model."""
		self.imageDescriber.toggleImageCaptioning(gesture)

	@scriptHandler.script(
		# Translators: Description for the open model manager script
		description=_("open model manager"),
		# Translators: Category of addon in input gestures.
		category=_("Caption Local"),
		gesture="kb:NVDA+windows+control+,"
	)
	def script_openManager(self, gesture) -> None:
		"""Script to open the model manager window."""
		try:
			self._openModelManager()
		except Exception as e:
			import ui
			ui.message(str(e))

	def _openModelManager(self) -> None:
		"""Open the model manager frame window."""
		def showManager() -> None:
			"""Show the model manager window."""
			try:
				if not self.managerFrame:
					self.managerFrame = ModelManagerFrame()
				
				self.managerFrame.Show()
				self.managerFrame.Raise()
				
			except Exception as e:
				import ui
				ui.message(str(e))
		
		# Ensure execution in main thread
		wx.CallAfter(showManager)
