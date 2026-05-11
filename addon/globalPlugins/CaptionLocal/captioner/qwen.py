# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2025 NV Access Limited, Tianze
# This file may be used under the terms of the GNU General Public License, version 2 or later, as modified by the NVDA license.
# For full terms and any additional permissions, see the NVDA license file: https://github.com/nvaccess/nvda/blob/master/copying.txt

import os
import subprocess
import tempfile
import io
from typing import Callable
from PIL import Image
from logHandler import log
from .base import ImageCaptioner

try:
	_
except NameError:
	_ = lambda x: x

try:
	from logHandler import log
	import addonHandler
	addonHandler.initTranslation()
except:
	pass

# Translators: default prompt for image captioning
DEFAULT_PROMPT = _("Please describe the picture in one sentence")


class QwenImageCaptioner(ImageCaptioner):
	"""Implementation of ImageCaptioner using miniqwen-cli.exe."""

	MAX_IMAGE_SIZE = 512

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
		onToken: Callable[[str], None] | None = None,
	) -> str:
		"""Generate image caption using CLI.

		:param image: Image file path or binary data.
		:param maxLength: Optional maximum tokens.
		:param onToken: Optional callback for each generated token.
		"""
		temp_file_path = None
		image_path = None

		try:
			# Load the image
			if isinstance(image, str) and os.path.exists(image):
				img = Image.open(image)
			elif isinstance(image, bytes):
				img = Image.open(io.BytesIO(image))
			else:
				# If it's a string but doesn't exist, it might be intended as bytes or error
				if isinstance(image, str):
					raise FileNotFoundError(f"Image file not found: {image}")
				raise ValueError(f"Unsupported image type: {type(image)}")

			# Resize if larger than MAX_IMAGE_SIZE
			width, height = img.size
			if max(width, height) > self.MAX_IMAGE_SIZE:
				img.thumbnail((self.MAX_IMAGE_SIZE, self.MAX_IMAGE_SIZE), Image.Resampling.LANCZOS)
				# Save to a temporary JPEG file
				with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
					if img.mode != "RGB":
						img = img.convert("RGB")
					img.save(tmp, format="JPEG")
					temp_file_path = tmp.name
					image_path = temp_file_path
			else:
				# If image is a string path and small enough, use it directly
				if isinstance(image, str):
					image_path = image
				else:
					# If it's bytes and small enough, still need to save to a temp file
					with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
						if img.mode != "RGB":
							img = img.convert("RGB")
						img.save(tmp, format="JPEG")
						temp_file_path = tmp.name
						image_path = temp_file_path
		except Exception as e:
			log.exception(f"Error processing image for Qwen: {e}")
			raise

		cmd = [
			self.cliPath,
			"--prompt", self.prompt,
			"--image", image_path,
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
			res_text = result.strip()
			if onToken and res_text:
				onToken(res_text)
			return res_text
		except subprocess.CalledProcessError as e:
			log.error(f"miniqwen-cli failed with exit code {e.returncode}: {e.output}")
			raise Exception(f"CLI error: {e.output}")
		except Exception as e:
			log.exception("Error running miniqwen-cli")
			raise
		finally:
			# Clean up temporary file if created
			if temp_file_path and os.path.exists(temp_file_path):
				try:
					os.remove(temp_file_path)
				except Exception:
					log.exception(f"Failed to remove temp file: {temp_file_path}")
