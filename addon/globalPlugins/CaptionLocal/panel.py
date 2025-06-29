# NVDA add-on: Caption Local
# Copyright (C) 2023 Cyrille Bougot
# This file is covered by the GNU General Public License.

from __future__ import unicode_literals

import wx

import gui
from gui import guiHelper, nvdaControls

import config
from logHandler import log
import addonHandler

# addonHandler.initTranslation()

# ADDON_SUMMARY = addonHandler.getCodeAddon().manifest["summary"]
ADDON_SUMMARY =  "caption  using local model"


def getBaseProfileConfigValue(*args):
	cfg = config.conf.profiles[0]
	for key in args:
		try:
			cfg = cfg[key]
		except KeyError:
			break
	else:
		validationFuncName = config.conf.getConfigValidation(tuple(args)).validationFuncName
		typeMaker = {
			'integer': int,
			'string': str,
			'option': str,
			'float': float,
		}.get(validationFuncName)
		if not typeMaker:
			raise NotImplementedError(validationFuncName)
		return typeMaker(cfg)
	return config.conf.getConfigValidation(tuple(args)).default

class CaptionLocalSettingsPanel(gui.settingsDialogs.SettingsPanel):
	title = ADDON_SUMMARY

	BACKUP_TYPES = [
		# Translators: This is a label of an item for the backup combo box in the NDTT Settings panel.
		('off', _('Off')),
		# Translators: This is a label of an item for the backup combo box in the NDTT Settings panel.
		('maxNumber', _('On')),
	]

	NO_DEFAULT_PROFILE_MESSAGE = _(
		# Translators: A message presented in the settings panel when opened while no-default profile is active.
		"{name} add-on can only be configured from the Normal Configuration profile.\n"
		"Please close this dialog, set your config profile to default and try again."
	).format(name=ADDON_SUMMARY)

	def makeSettings(self, settingsSizer):
		if config.conf.profiles[-1].name is not None or len(config.conf.profiles) != 1:
			self.panelDescription = self.NO_DEFAULT_PROFILE_MESSAGE
			helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
			textItem = helper.addItem(wx.StaticText(self, label=self.panelDescription.replace('&', '&&')))
			textItem.Wrap(self.scaleSize(544))
			return
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		# Translators: This is a label for an edit field in the CaptionLocal Settings panel.
		modelPathLabel = _("model path")

		groupSizer = wx.StaticBoxSizer(wx.VERTICAL, self, label=modelPathLabel)
		groupBox = groupSizer.GetStaticBox()
		groupHelper = sHelper.addItem(gui.guiHelper.BoxSizerHelper(self, sizer=groupSizer))
		# Translators: The label of a button to browse for a directory or a file.
		browseText = _("Browse...")
		# Translators: The title of the dialog presented when browsing for the directory.
		dirDialogTitle = _("Select a directory")
		directoryPathHelper = gui.guiHelper.PathSelectionHelper(groupBox, browseText, dirDialogTitle)
		directoryEntryControl = groupHelper.addItem(directoryPathHelper)
		self.modelPathEdit = directoryEntryControl.pathControl
		self.modelPathEdit.Value = config.conf['captionLocal']['localModelPath']

		# Translators: This is a label for the combo box in the NDTT Settings panel.
		# text = _("Backup of old logs:")
		# self.makeBackupsList = sHelper.addLabeledControl(
			# text,
			# wx.Choice,
			# choices=[label for val, label in self.BACKUP_TYPES],
		# )
		# val = getBaseProfileConfigValue('captionLocal', 'logBackup')
		# index = [v for v, l in self.BACKUP_TYPES].index(val)
		# self.makeBackupsList.Select(index)
		# backupType = self.BACKUP_TYPES[index][0]
		# self.makeBackupsList.Bind(wx.EVT_CHOICE, self.onMakeBackupsListItemChanged)

		# minNbBackups = int(self.getParameterBound("logBackupMaxNumber", "min"))
		# maxNbBackups = int(self.getParameterBound("logBackupMaxNumber", "max"))

		# Translators: This is a label for a setting in the settings panel
		# text = _("Limit the number of backups to:")
		# self.nbBackupsEdit = sHelper.addLabeledControl(
			# text,
			# nvdaControls.SelectOnFocusSpinCtrl,
			# min=minNbBackups,
			# max=maxNbBackups,
			# initial=getBaseProfileConfigValue('captionLocal', 'logBackupMaxNumber'),
		# )
		# self.updateNbBackupsEdit(backupType)

	@staticmethod
	def getParameterBound(name, boundType):
		"""Gets the bound of a parameter in the "ndtt" section of the config.
		@param name: the name of the paremeter
		@type name: str
		@param boundType: "min" or "max"
		@type boundType: str
		"""

		try:
			return config.conf.getConfigValidation(("ndtt", name)).kwargs[boundType]
		except TypeError:
			# For older version of configObj (e.g. used in NVDA 2019.2.1)
			return config.conf.getConfigValidationParameter(["ndtt", name], boundType)

	def onMakeBackupsListItemChanged(self, evt):
		index = evt.GetSelection()
		self.updateNbBackupsEdit(self.BACKUP_TYPES[index][0])

	def updateNbBackupsEdit(self, backupType):
		self.nbBackupsEdit.Enable(backupType == 'maxNumber')

	def onSave(self):
		# Make sure we're operating in the "normal" profile
		if config.conf.profiles[-1].name is None and len(config.conf.profiles) == 1:

			config.conf['captionLocal']['localModelPath'] = self.modelPathEdit.GetValue()
			# config.conf['captionLocal']['logBackup'] = self.BACKUP_TYPES[self.makeBackupsList.Selection][0]
			# config.conf['captionLocal']['logBackupMaxNumber'] = int(self.nbBackupsEdit.Value)
		else:
			log.debugWarning('No configuration saved for NDTT since the current profile is not the default one.')
