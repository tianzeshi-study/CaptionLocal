# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2025 NV Access Limited, Tianze
# This file may be used under the terms of the GNU General Public License, version 2 or later, as modified by the NVDA license.
# For full terms and any additional permissions, see the NVDA license file: https://github.com/nvaccess/nvda/blob/master/copying.txt

import wx
import os
import threading
import json
import urllib.request
from typing import List, Tuple, Optional
import winsound

from .modelDownloader import ModelDownloader

try:
	from logHandler import log
	import addonHandler
	addonHandler.initTranslation()
except:
	pass

MODELS_CONFIG_URL = "https://raw.githubusercontent.com/tianzeshi-study/CaptionLocal/master/addon/globalPlugins/CaptionLocal/models.json"
MODELS_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "models.json")


def _closeWindowOnEscape(window: wx.TopLevelWindow) -> None:
	if isinstance(window, wx.Dialog) and window.IsModal():
		window.EndModal(wx.ID_CANCEL)
		return
	window.Close()


def _bindEscapeToClose(window: wx.TopLevelWindow) -> None:
	def onCharHook(event: wx.KeyEvent) -> None:
		if event.GetKeyCode() == wx.WXK_ESCAPE:
			_closeWindowOnEscape(window)
			return
		event.Skip()

	window.Bind(wx.EVT_CHAR_HOOK, onCharHook)

class AdvancedSettingsDialog(wx.Dialog):
	"""Advanced Settings Dialog for model download configuration."""
	
	def __init__(self, parent, modelName: str = "Xenova/vit-gpt2-image-captioning", 
				 filesList: Optional[List[str]] = None, resolvePath: str = "/resolve/main", 
				 useMirror: bool = False):
		super().__init__(parent, title=_("Advanced Settings"), size=(500, 400),
						style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		
		self.modelName = modelName
		self.filesList = filesList or [
			"onnx/encoder_model_quantized.onnx",
			"onnx/decoder_model_merged_quantized.onnx", 
			"config.json",
			"vocab.json",
			"preprocessor_config.json"
		]
		self.resolvePath = resolvePath
		self.useMirror = useMirror
		
		self._initUI()
		self._bindEvents()
		_bindEscapeToClose(self)
		
	def _initUI(self):
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		notebook = wx.Notebook(self)
		
		modelPanel = wx.Panel(notebook)
		modelSizer = wx.BoxSizer(wx.VERTICAL)
		modelSizer.Add(wx.StaticText(modelPanel, label=_("Model Name:")), 0, wx.ALL, 5)
		self.modelNameCtrl = wx.TextCtrl(modelPanel, value=self.modelName, size=(400, -1))
		modelSizer.Add(self.modelNameCtrl, 0, wx.ALL | wx.EXPAND, 5)
		
		modelSizer.Add(wx.StaticText(modelPanel, label=_("Resolve Path:")), 0, wx.ALL, 5)
		self.resolvePathCtrl = wx.TextCtrl(modelPanel, value=self.resolvePath, size=(400, -1))
		modelSizer.Add(self.resolvePathCtrl, 0, wx.ALL | wx.EXPAND, 5)
		
		self.useMirrorCb = wx.CheckBox(modelPanel, label=_("Use Mirror (hf-mirror.com)"))
		self.useMirrorCb.SetValue(self.useMirror)
		modelSizer.Add(self.useMirrorCb, 0, wx.ALL, 5)
		
		modelPanel.SetSizer(modelSizer)
		notebook.AddPage(modelPanel, _("Model Config"))
		
		filesPanel = wx.Panel(notebook)
		filesSizer = wx.BoxSizer(wx.VERTICAL)
		filesSizer.Add(wx.StaticText(filesPanel, label=_("Files to Download:")), 0, wx.ALL, 5)
		self.filesListbox = wx.ListBox(filesPanel, choices=self.filesList, style=wx.LB_MULTIPLE | wx.LB_HSCROLL)
		for i in range(len(self.filesList)):
			self.filesListbox.SetSelection(i)
		filesSizer.Add(self.filesListbox, 1, wx.ALL | wx.EXPAND, 5)
		
		fileBtnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.addFileBtn = wx.Button(filesPanel, label=_("Add File"))
		self.removeFileBtn = wx.Button(filesPanel, label=_("Remove File"))
		fileBtnSizer.Add(self.addFileBtn, 0, wx.ALL, 2)
		fileBtnSizer.Add(self.removeFileBtn, 0, wx.ALL, 2)
		filesSizer.Add(fileBtnSizer, 0, wx.ALL | wx.CENTER, 5)
		
		filesPanel.SetSizer(filesSizer)
		notebook.AddPage(filesPanel, _("File List"))
		
		mainSizer.Add(notebook, 1, wx.ALL | wx.EXPAND, 10)
		
		btnSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		mainSizer.Add(btnSizer, 0, wx.ALL | wx.CENTER, 10)
		self.SetSizer(mainSizer)
		
	def _bindEvents(self):
		self.addFileBtn.Bind(wx.EVT_BUTTON, self.onAddFile)
		self.removeFileBtn.Bind(wx.EVT_BUTTON, self.onRemoveFile)
		
	def onAddFile(self, event):
		dlg = wx.TextEntryDialog(self, _("Enter file path:"), _("Add File"))
		_bindEscapeToClose(dlg)
		if dlg.ShowModal() == wx.ID_OK:
			filePath = dlg.GetValue().strip()
			if filePath and filePath not in self.filesList:
				self.filesList.append(filePath)
				self.filesListbox.Append(filePath)
				self.filesListbox.SetSelection(len(self.filesList) - 1)
		dlg.Destroy()
		
	def onRemoveFile(self, event):
		selection = self.filesListbox.GetSelections()
		for s in sorted(selection, reverse=True):
			self.filesList.pop(s)
			self.filesListbox.Delete(s)
			
	def getSettings(self) -> dict:
		selectedFiles = []
		for i in range(self.filesListbox.GetCount()):
			if self.filesListbox.IsSelected(i):
				selectedFiles.append(self.filesList[i])
		
		return {
			'modelName': self.modelNameCtrl.GetValue().strip(),
			'filesToDownload': selectedFiles,
			'resolvePath': self.resolvePathCtrl.GetValue().strip(),
			'useMirror': self.useMirrorCb.GetValue()
		}


class SoundNotification:
	@staticmethod
	def playStart():
		try: winsound.MessageBeep(winsound.MB_ICONASTERISK)
		except: pass
	
	@staticmethod
	def playSuccess():
		try: winsound.MessageBeep(winsound.MB_OK)
		except: pass
	
	@staticmethod
	def playError():
		try: winsound.MessageBeep(winsound.MB_ICONHAND)
		except: pass
	
	@staticmethod
	def playWarning():
		try: winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
		except: pass


class ModelManagerFrame(wx.Frame):
	"""Model Manager Main Frame."""
	
	def __init__(self):
		super().__init__(None, title=_("Model Manager"), size=(600, 520))
		
		self.modelsConfig = []
		self._loadLocalConfig()
		
		self.modelName = "Xenova/vit-gpt2-image-captioning"
		self.filesToDownload = [
			"onnx/encoder_model_quantized.onnx",
			"onnx/decoder_model_merged_quantized.onnx", 
			"config.json",
			"vocab.json",
			"preprocessor_config.json"
		]
		self.resolvePath = "/resolve/main"
		self.useMirror = False
		
		if self.modelsConfig:
			self._applyModelConfig(self.modelsConfig[0])
		
		self.downloader = None
		self.downloadThread = None
		
		self._initUI()
		self._initDefaultPath()
		self._bindEvents()
		_bindEscapeToClose(self)
		self.Centre()
		
	def _initUI(self):
		panel = wx.Panel(self)
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		
		titleText = wx.StaticText(panel, label=_("Model Download Manager"))
		titleFont = titleText.GetFont()
		titleFont.PointSize += 4
		titleFont = titleFont.Bold()
		titleText.SetFont(titleFont)
		mainSizer.Add(titleText, 0, wx.ALL | wx.CENTER, 15)
		
		modelBox = wx.StaticBoxSizer(wx.StaticBox(panel, label=_("Model Selection")), wx.VERTICAL)
		modelSizer = wx.BoxSizer(wx.HORIZONTAL)
		modelSizer.Add(wx.StaticText(panel, label=_("Select Model:")), 0, wx.ALL | wx.CENTER, 5)
		
		choices = [m.get("name", m.get("id", "Unknown")) for m in self.modelsConfig]
		self.modelCombo = wx.ComboBox(panel, choices=choices, style=wx.CB_READONLY)
		if choices:
			self.modelCombo.SetSelection(0)
		modelSizer.Add(self.modelCombo, 1, wx.ALL | wx.EXPAND, 5)
		
		self.updateConfigBtn = wx.Button(panel, label=_("Update Models List"))
		modelSizer.Add(self.updateConfigBtn, 0, wx.ALL, 5)
		modelBox.Add(modelSizer, 0, wx.ALL | wx.EXPAND, 5)
		mainSizer.Add(modelBox, 0, wx.ALL | wx.EXPAND, 10)
		
		pathBox = wx.StaticBoxSizer(wx.StaticBox(panel, label=_("Model Directory Settings")), wx.VERTICAL)
		pathSizer = wx.BoxSizer(wx.HORIZONTAL)
		pathSizer.Add(wx.StaticText(panel, label=_("Models Directory:")), 0, wx.ALL | wx.CENTER, 5)
		self.pathCtrl = wx.TextCtrl(panel, size=(350, -1))
		pathSizer.Add(self.pathCtrl, 1, wx.ALL | wx.EXPAND, 5)
		self.browseBtn = wx.Button(panel, label=_("Browse..."))
		pathSizer.Add(self.browseBtn, 0, wx.ALL, 5)
		pathBox.Add(pathSizer, 0, wx.ALL | wx.EXPAND, 5)
		mainSizer.Add(pathBox, 0, wx.ALL | wx.EXPAND, 10)
		
		infoBox = wx.StaticBoxSizer(wx.StaticBox(panel, label=_("Model Information")), wx.VERTICAL)
		self.modelInfoText = wx.StaticText(panel, label=_("Model: {modelName}").format(modelName=self.modelName))
		infoBox.Add(self.modelInfoText, 0, wx.ALL, 5)
		self.filesInfoText = wx.StaticText(panel, label=_("File Count: {count}").format(count=len(self.filesToDownload)))
		infoBox.Add(self.filesInfoText, 0, wx.ALL, 5)
		mainSizer.Add(infoBox, 0, wx.ALL | wx.EXPAND, 10)
		
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.advancedBtn = wx.Button(panel, label=_("Advanced Settings..."))
		self.setActiveBtn = wx.Button(panel, label=_("Set as Active Model"))
		btnSizer.Add(self.advancedBtn, 0, wx.ALL, 5)
		btnSizer.Add(self.setActiveBtn, 0, wx.ALL, 5)
		btnSizer.AddStretchSpacer(1)
		self.downloadBtn = wx.Button(panel, label=_("Start Download"), size=(120, 35))
		btnSizer.Add(self.downloadBtn, 0, wx.ALL, 5)
		mainSizer.Add(btnSizer, 0, wx.ALL | wx.EXPAND, 10)
		
		self.statusText = wx.StaticText(panel, label=_("Ready"))
		mainSizer.Add(self.statusText, 0, wx.ALL | wx.EXPAND, 10)
		
		logBox = wx.StaticBoxSizer(wx.StaticBox(panel, label=_("Download Log")), wx.VERTICAL)
		self.logText = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(550, 150))
		logBox.Add(self.logText, 1, wx.ALL | wx.EXPAND, 5)
		mainSizer.Add(logBox, 1, wx.ALL | wx.EXPAND, 10)
		
		panel.SetSizer(mainSizer)
		
	def _initDefaultPath(self):
		import config
		try:
			defaultPath = config.conf["captionLocal"]["modelsDir"]
			self.pathCtrl.SetValue(defaultPath)
		except:
			pass
			
	def _loadLocalConfig(self):
		try:
			if os.path.exists(MODELS_CONFIG_FILE):
				with open(MODELS_CONFIG_FILE, "r", encoding="utf-8") as f:
					data = json.load(f)
					self.modelsConfig = data.get("models", [])
		except Exception as e:
			print(f"Error loading local models config: {e}")

	def _applyModelConfig(self, modelData):
		self.modelName = modelData.get("id", "Unknown")
		self.filesToDownload = modelData.get("files", [])
		self.resolvePath = modelData.get("resolvePath", "/resolve/main")

	def _bindEvents(self):
		self.browseBtn.Bind(wx.EVT_BUTTON, self.onBrowsePath)
		self.advancedBtn.Bind(wx.EVT_BUTTON, self.onAdvancedSettings)
		self.setActiveBtn.Bind(wx.EVT_BUTTON, self.onSetActive)
		self.downloadBtn.Bind(wx.EVT_BUTTON, self.onDownload)
		self.modelCombo.Bind(wx.EVT_COMBOBOX, self.onModelSelect)
		self.updateConfigBtn.Bind(wx.EVT_BUTTON, self.onUpdateConfig)
		self.Bind(wx.EVT_CLOSE, self.onClose)
		
	def log(self, message: str):
		wx.CallAfter(self._logSafe, message)
		
	def _logSafe(self, message: str):
		if not self.IsBeingDeleted():
			self.logText.AppendText(f"{message}\n")
			self.logText.SetInsertionPointEnd()
			
	def updateStatus(self, status: str):
		wx.CallAfter(self._updateStatusSafe, status)
		
	def _updateStatusSafe(self, status: str):
		if not self.IsBeingDeleted():
			self.statusText.SetLabel(status)
			
	def updateProgress(self, fileName: str, downloaded: int, total: int, progressPercent: float):
		self.log(_("file: {fileName}  progress: {progress:.2f}%").format(fileName=fileName, progress=progressPercent))
	
	def onBrowsePath(self, event):
		dlg = wx.DirDialog(self, _("Select Download Directory"), defaultPath=self.pathCtrl.GetValue())
		_bindEscapeToClose(dlg)
		if dlg.ShowModal() == wx.ID_OK:
			self.pathCtrl.SetValue(dlg.GetPath())
		dlg.Destroy()
		
	def onAdvancedSettings(self, event):
		dlg = AdvancedSettingsDialog(self, self.modelName, self.filesToDownload, self.resolvePath, self.useMirror)
		if dlg.ShowModal() == wx.ID_OK:
			settings = dlg.getSettings()
			self.modelName = settings['modelName']
			self.filesToDownload = settings['filesToDownload']
			self.resolvePath = settings['resolvePath']
			self.useMirror = settings['useMirror']
			self.modelInfoText.SetLabel(_("Model: {modelName}").format(modelName=self.modelName))
			self.filesInfoText.SetLabel(_("File Count: {count}").format(count=len(self.filesToDownload)))
		dlg.Destroy()
		
	def onModelSelect(self, event):
		sel = self.modelCombo.GetSelection()
		if sel != wx.NOT_FOUND and sel < len(self.modelsConfig):
			self._applyModelConfig(self.modelsConfig[sel])
			self.modelInfoText.SetLabel(_("Model: {modelName}").format(modelName=self.modelName))
			self.filesInfoText.SetLabel(_("File Count: {count}").format(count=len(self.filesToDownload)))

	def onUpdateConfig(self, event):
		self.updateConfigBtn.Disable()
		self.statusText.SetLabel(_("Updating models list..."))
		threading.Thread(target=self._updateConfigWorker, daemon=True).start()
		
	def onSetActive(self, event):
		import config
		from logHandler import log
		try:
			config.conf["captionLocal"]["modelsDir"] = self.pathCtrl.GetValue()
			config.conf["captionLocal"]["currentModel"] = self.modelName
			self.log(_("✅ Active model set to: {modelName}").format(modelName=self.modelName))
			SoundNotification.playSuccess()
		except Exception as e:
			log.error(f"Failed to set active model: {e}")
			self.log(_("❌ Failed to set active model."))
			SoundNotification.playError()

	def _updateConfigWorker(self):
		try:
			req = urllib.request.Request(MODELS_CONFIG_URL, headers={'User-Agent': 'Mozilla/5.0'})
			with urllib.request.urlopen(req, timeout=10) as response:
				data = json.loads(response.read().decode('utf-8'))
				if "models" in data:
					with open(MODELS_CONFIG_FILE, "w", encoding="utf-8") as f:
						json.dump(data, f, indent='\t', ensure_ascii=False)
					wx.CallAfter(self._updateConfigSuccess, data["models"])
				else:
					wx.CallAfter(self._updateConfigFail, _("Invalid configuration format."))
		except Exception as e:
			wx.CallAfter(self._updateConfigFail, str(e))
			
	def _updateConfigSuccess(self, models):
		self.modelsConfig = models
		choices = [m.get("name", m.get("id", "Unknown")) for m in self.modelsConfig]
		self.modelCombo.Clear()
		self.modelCombo.AppendItems(choices)
		if choices:
			self.modelCombo.SetSelection(0)
			self._applyModelConfig(self.modelsConfig[0])
			self.modelInfoText.SetLabel(_("Model: {modelName}").format(modelName=self.modelName))
			self.filesInfoText.SetLabel(_("File Count: {count}").format(count=len(self.filesToDownload)))
		self.statusText.SetLabel(_("Models list updated successfully."))
		self.updateConfigBtn.Enable()
		SoundNotification.playSuccess()

	def _updateConfigFail(self, error):
		self.statusText.SetLabel(_("Failed to update models list: {error}").format(error=error))
		self.updateConfigBtn.Enable()
		SoundNotification.playError()

	def onDownload(self, event):
		if self.downloadThread and self.downloadThread.is_alive():
			if self.downloader:
				self.downloader.requestCancel()
				self.log(_("Cancelling download..."))
			return
			
		self.downloadBtn.SetLabel(_("Cancel Download"))
		SoundNotification.playStart()
		self.downloadThread = threading.Thread(target=self._downloadWorker)
		self.downloadThread.daemon = True
		self.downloadThread.start()
		
	def _downloadWorker(self):
		try:
			self.updateStatus(_("Downloading..."))
			remoteHost = "hf-mirror.com" if self.useMirror else "huggingface.co"
			self.downloader = ModelDownloader(remoteHost=remoteHost)
			
			downloadPath = self.pathCtrl.GetValue()
			# Models are saved to downloadPath/modelName
			successful, failed = self.downloader.downloadModelsMultithreaded(
				modelsDir=downloadPath,
				modelName=self.modelName,
				filesToDownload=self.filesToDownload,
				resolvePath=self.resolvePath,
				progressCallback=self.updateProgress
			)
			
			if self.downloader.cancelRequested:
				self.log(_("Download cancelled."))
				self.updateStatus(_("Cancelled"))
			elif not failed:
				self.log(_("✅ All files downloaded successfully!"))
				self.updateStatus(_("Completed"))
				SoundNotification.playSuccess()
				# Update config with the new path if it was changed
				import config
				config.conf["captionLocal"]["modelsDir"] = downloadPath
				config.conf["captionLocal"]["currentModel"] = self.modelName
			else:
				self.log(_("❌ Download failed for some files."))
				self.updateStatus(_("Failed"))
				SoundNotification.playError()
		except Exception as e:
			self.log(_("Error: {error}").format(error=e))
			self.updateStatus(_("Error"))
			SoundNotification.playError()
		finally:
			wx.CallAfter(self._downloadFinished)
			
	def _downloadFinished(self):
		self.downloadBtn.SetLabel(_("Start Download"))
		
	def onClose(self, event):
		if self.downloadThread and self.downloadThread.is_alive():
			if self.downloader:
				self.downloader.requestCancel()
		self.Destroy()
