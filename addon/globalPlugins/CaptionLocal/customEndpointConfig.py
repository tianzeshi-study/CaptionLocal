# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2025 NV Access Limited, Tianze
# This file may be used under the terms of the GNU General Public License, version 2 or later, as modified by the NVDA license.
# For full terms and any additional permissions, see the NVDA license file: https://github.com/nvaccess/nvda/blob/master/copying.txt

import wx
import json
import os
from logHandler import log

try:
	_
except NameError:
	_ = lambda x: x

class CustomEndpointConfigDialog(wx.Dialog):
	"""Dialog for configuring custom API endpoints."""
	
	def __init__(self, parent, config_path):
		super().__init__(parent, title=_("Configure Custom Endpoint"), size=(500, 350))
		self.config_path = config_path
		self.config_data = {}
		self._load_existing_config()
		self._initUI()
		
	def _load_existing_config(self):
		if os.path.exists(self.config_path):
			try:
				with open(self.config_path, "r", encoding="utf-8") as f:
					self.config_data = json.load(f)
			except Exception:
				log.exception(f"Failed to load config from {self.config_path}")

	def _initUI(self):
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		
		flexSizer = wx.FlexGridSizer(rows=4, cols=2, vgap=10, hgap=10)
		flexSizer.AddGrowableCol(1)
		
		# Endpoint URL
		flexSizer.Add(wx.StaticText(self, label=_("Endpoint URL:")), 0, wx.ALIGN_CENTER_VERTICAL)
		self.endpointCtrl = wx.TextCtrl(self, value=self.config_data.get("endpoint", "https://api.openai.com/v1"))
		flexSizer.Add(self.endpointCtrl, 1, wx.EXPAND)
		
		# API Key
		flexSizer.Add(wx.StaticText(self, label=_("API Key:")), 0, wx.ALIGN_CENTER_VERTICAL)
		self.apiKeyCtrl = wx.TextCtrl(self, value=self.config_data.get("api_key", ""), style=wx.TE_PASSWORD)
		flexSizer.Add(self.apiKeyCtrl, 1, wx.EXPAND)
		
		# Model Name
		flexSizer.Add(wx.StaticText(self, label=_("Model Name:")), 0, wx.ALIGN_CENTER_VERTICAL)
		self.modelCtrl = wx.TextCtrl(self, value=self.config_data.get("model", "gpt-4o-mini"))
		flexSizer.Add(self.modelCtrl, 1, wx.EXPAND)

		# Custom Prompt
		flexSizer.Add(wx.StaticText(self, label=_("Custom Prompt (Optional):")), 0, wx.ALIGN_CENTER_VERTICAL)
		self.promptCtrl = wx.TextCtrl(self, value=self.config_data.get("prompt", ""))
		flexSizer.Add(self.promptCtrl, 1, wx.EXPAND)
		
		mainSizer.Add(flexSizer, 1, wx.ALL | wx.EXPAND, 15)
		
		# Buttons
		btnSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		mainSizer.Add(btnSizer, 0, wx.ALL | wx.CENTER, 10)
		
		self.SetSizer(mainSizer)
		
	def get_config(self):
		return {
			"architectures": ["CustomEndpoint"],
			"endpoint": self.endpointCtrl.GetValue().strip(),
			"api_key": self.apiKeyCtrl.GetValue().strip(),
			"model": self.modelCtrl.GetValue().strip(),
			"prompt": self.promptCtrl.GetValue().strip() or None
		}

def show_config_dialog(parent, config_path):
	"""Show the config dialog and save if OK is pressed."""
	dlg = CustomEndpointConfigDialog(parent, config_path)
	if dlg.ShowModal() == wx.ID_OK:
		config = dlg.get_config()
		# Ensure directory exists
		os.makedirs(os.path.dirname(config_path), exist_ok=True)
		with open(config_path, "w", encoding="utf-8") as f:
			json.dump(config, f, indent=4, ensure_ascii=False)
		return True
	return False

def is_config_valid(config_path):
	"""Check if the config file exists and has the required fields."""
	if not os.path.exists(config_path):
		return False
	try:
		with open(config_path, "r", encoding="utf-8") as f:
			config = json.load(f)
		return all(k in config for k in ["endpoint", "model"])
	except Exception:
		return False
