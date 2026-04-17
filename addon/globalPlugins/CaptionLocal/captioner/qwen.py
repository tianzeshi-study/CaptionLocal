# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2025 NV Access Limited, Tianze
# This file may be used under the terms of the GNU General Public License, version 2 or later, as modified by the NVDA license.
# For full terms and any additional permissions, see the NVDA license file: https://github.com/nvaccess/nvda/blob/master/copying.txt

import os
import subprocess
import base64
from logHandler import log
from .base import ImageCaptioner

try:
	_
except NameError:
	_ = lambda x: x

# Translators: default prompt for image captioning
DEFAULT_PROMPT = _("请一句话描述图片")


class QwenImageCaptioner(ImageCaptioner):
	"""Implementation of ImageCaptioner using miniqwen-cli.exe."""

	def __init__(
		self,
		modelDir: str,
		prompt: str | None = None,
		enableThinking: bool = False,
	):
		"""Initialize the Qwen image captioner.

		:param modelDir: Path to the model directory.
		:param prompt: Optional custom prompt.
		:param enableThinking: Whether to enable thinking mode.
		"""
		self.modelDir = modelDir
		self.prompt = prompt or DEFAULT_PROMPT
		self.enableThinking = enableThinking
		
		# miniqwen-cli.exe is in ../libs/bin relative to this file's directory
		baseDir = os.path.dirname(os.path.dirname(__file__))
		self.cliPath = os.path.join(baseDir, "libs", "bin", "miniqwen-cli.exe")

	def generateCaption(
		self,
		image: str | bytes,
		maxLength: int | None = None,
	) -> str:
		"""Generate image caption using CLI.
		
		:param image: Image file path or binary data.
		:param maxLength: Optional maximum tokens.
		"""
		if isinstance(image, bytes):
			imgData = image
		else:
			with open(image, "rb") as f:
				imgData = f.read()

		imgB64 = base64.b64encode(imgData).decode("utf-8")

		cmd = [
			self.cliPath,
			"--prompt", self.prompt,
			"--base64-image", imgB64,
			"--model-dir", self.modelDir,
		]

		if self.enableThinking:
			cmd.append("--enable-thinking")

		if maxLength:
			cmd.extend(["--max-tokens", str(maxLength)])

		try:
			# Use startupinfo to hide the console window on Windows
			startupinfo = subprocess.STARTUPINFO()
			startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

			result = subprocess.check_output(
				cmd,
				stderr=subprocess.STDOUT,
				universal_newlines=True,
				encoding="utf-8",
				startupinfo=startupinfo,
			)
			return result.strip()
		except subprocess.CalledProcessError as e:
			log.error(f"miniqwen-cli failed with exit code {e.returncode}: {e.output}")
			raise Exception(f"CLI error: {e.output}")
		except Exception as e:
			log.exception("Error running miniqwen-cli")
			raise
