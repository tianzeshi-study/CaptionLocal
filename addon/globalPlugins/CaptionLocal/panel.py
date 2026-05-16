# -*- coding: UTF-8 -*-
# NVDA add-on: Caption Local
# Copyright (C) 
# This file is covered by the GNU General Public License.

from __future__ import unicode_literals

from typing import Optional
import wx

import gui
from gui import guiHelper, nvdaControls

import config
from logHandler import log
import addonHandler


try:
	addonHandler.initTranslation()
	ADDON_SUMMARY = addonHandler.getCodeAddon().manifest["summary"]
except:
	ADDON_SUMMARY = "caption using local model"


class CaptionLocalSettingsPanel(gui.settingsDialogs.SettingsPanel):
	"""Settings panel for Caption Local add-on configuration.
	
	This panel allows users to configure the local model path and 
	initialization settings for the Caption Local add-on.
	"""
	
	title = ADDON_SUMMARY

	# Translators: A message presented in the settings panel when opened while no-default profile is active.
	NO_DEFAULT_PROFILE_MESSAGE = _(
		"{name} add-on can only be configured from the Normal Configuration profile.\n"
		"Please close this dialog, set your config profile to default and try again."
	).format(name=ADDON_SUMMARY)

	def makeSettings(self, settingsSizer: wx.Sizer) -> None:
		"""Create the settings controls for the panel.
		
		Args:
			settingsSizer: The sizer to add settings controls to.
		"""
		if config.conf.profiles[-1].name is not None or len(config.conf.profiles) != 1:
			self.panelDescription = self.NO_DEFAULT_PROFILE_MESSAGE
			helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
			textItem = helper.addItem(wx.StaticText(self, label=self.panelDescription.replace('&', '&&')))
			textItem.Wrap(self.scaleSize(544))
			return
		
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		
		# Translators: A setting in addon settings dialog.
		self.loadModelWhenInit = sHelper.addItem(wx.CheckBox(self, label=_("load model when init (may cause high use of memory)")))
		self.loadModelWhenInit.SetValue(config.conf['captionLocal']['loadModelWhenInit'])

		# Translators: A setting in addon settings dialog.
		self.copyToClipboard = sHelper.addItem(wx.CheckBox(self, label=_("Copy result to clipboard automatically")))
		self.copyToClipboard.SetValue(config.conf['captionLocal'].get('copyToClipboard', False))

	def onSave(self) -> None:
		"""Save the configuration settings.
		
		Only saves if operating in the default profile to prevent 
		configuration issues with custom profiles.
		"""
		# Make sure we're operating in the "normal" profile
		if config.conf.profiles[-1].name is None and len(config.conf.profiles) == 1:
			config.conf['captionLocal']['loadModelWhenInit'] = self.loadModelWhenInit.GetValue()
			config.conf['captionLocal']['copyToClipboard'] = self.copyToClipboard.GetValue()
		else:
			log.debugWarning('No configuration saved for CaptionLocal since the current profile is not the default one.')
