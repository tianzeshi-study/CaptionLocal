# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2025 NV Access Limited, Tianze
# This file may be used under the terms of the GNU General Public License, version 2 or later, as modified by the NVDA license.
# For full terms and any additional permissions, see the NVDA license file: https://github.com/nvaccess/nvda/blob/master/copying.txt

import os
import sys
import json
import zipfile
import io
import requests
import threading
from typing import Callable, List, Optional, Dict
from logHandler import log

try:
	_
except NameError:
	_ = lambda x: x

# Type for progress callback: (fileName, downloadedBytes, totalBytes, percentage)
ProgressCallback = Callable[[str, int, int, float], None]

MODELS_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "models.json")
LIBS_DIR = os.path.join(os.path.dirname(__file__), "libs")

class DependencyManager:
	"""Manages runtime dependencies (Python packages and binaries)."""

	def __init__(self):
		self.runtimes = {}
		self._load_config()

	def _load_config(self):
		try:
			if os.path.exists(MODELS_CONFIG_FILE):
				with open(MODELS_CONFIG_FILE, "r", encoding="utf-8") as f:
					data = json.load(f)
					self.runtimes = data.get("runtimes", {})
					self.models = data.get("models", [])
		except Exception:
			log.exception("Failed to load runtimes config")

	def get_required_runtimes(self, model_id: str) -> List[str]:
		"""Get a list of runtime IDs required by a model."""
		for m in self.models:
			if m.get("id") == model_id:
				return m.get("runtime_dependencies", [])
		return []

	def is_runtime_installed(self, runtime_id: str) -> bool:
		"""Check if a runtime is already installed in the libs directory."""
		if runtime_id == "onnxruntime":
			# Check for onnxruntime package directory
			return os.path.exists(os.path.join(LIBS_DIR, "onnxruntime"))
		elif runtime_id == "miniqinference":
			# Check for the binary specifically
			cli_path = os.path.join(LIBS_DIR, "bin", "miniqwen-cli.exe")
			return os.path.exists(cli_path)
		return False

	def download_and_install(self, runtime_id: str, progress_callback: Optional[ProgressCallback] = None) -> bool:
		"""Download and install a runtime dependency."""
		info = self.runtimes.get(runtime_id)
		if not info:
			log.error(f"Unknown runtime: {runtime_id}")
			return False

		if info.get("type") == "pypi":
			return self._install_from_pypi(runtime_id, info, progress_callback)
		
		return False

	def _install_from_pypi(self, runtime_id: str, info: dict, progress_callback: Optional[ProgressCallback]) -> bool:
		package_name = info.get("package", runtime_id).split("[")[0] # Remove extras
		
		# Get correct version based on Python version if specified
		version = info.get("version")
		py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
		if "versions" in info:
			version = info["versions"].get(py_ver, version)

		try:
			# 1. Fetch metadata from PyPI
			url = f"https://pypi.org/pypi/{package_name}/json"
			if version:
				url = f"https://pypi.org/pypi/{package_name}/{version}/json"
			
			resp = requests.get(url, timeout=10)
			resp.raise_for_status()
			data = resp.json()
			
			# 2. Find best matching wheel
			# Targets: win_amd64 and current python version
			releases = data.get("urls", [])
			best_url = None
			file_size = 0
			
			py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
			# Also consider universal wheels or those with correct abi tags
			
			for release in releases:
				filename = release.get("filename", "")
				if not filename.endswith(".whl"):
					continue
				if "win_amd64" not in filename:
					continue
				
				# Check python version compatibility in filename
				# e.g., onnxruntime-1.19.2-cp311-cp311-win_amd64.whl
				parts = filename.split("-")
				if len(parts) < 5: continue
				
				file_py_tag = parts[2]
				if file_py_tag == "py3" or py_tag in file_py_tag:
					best_url = release.get("url")
					file_size = release.get("size", 0)
					break
			
			if not best_url:
				log.error(f"Could not find compatible wheel for {package_name} on {py_tag} win_amd64")
				return False

			# 3. Download the wheel
			if progress_callback:
				progress_callback(filename, 0, file_size, 0.0)

			download_resp = requests.get(best_url, stream=True, timeout=30)
			download_resp.raise_for_status()
			
			content = io.BytesIO()
			downloaded = 0
			for chunk in download_resp.iter_content(chunk_size=8192):
				if chunk:
					content.write(chunk)
					downloaded += len(chunk)
					if progress_callback:
						progress_callback(filename, downloaded, file_size, (downloaded/file_size)*100 if file_size else 0)

			# 4. Unzip into libs
			content.seek(0)
			with zipfile.ZipFile(content) as zf:
				# Filter out metadata and unnecessary files if desired, but for now just extract all
				zf.extractall(LIBS_DIR)
			
			# Special post-install for miniqinference to move the exe if needed
			if runtime_id == "miniqinference":
				self._fix_miniqinference_paths()

			return True

		except Exception:
			log.exception(f"Failed to install {runtime_id} from PyPI")
			return False

	def _fix_miniqinference_paths(self):
		"""miniqinference might put the exe in a subfolder or need to be moved to libs/bin."""
		# In wheel, scripts usually go to {package}-{version}.data/scripts/
		# But since we are extracting to LIBS_DIR, we need to find it.
		# Search for miniqwen-cli.exe in extracted files
		for root, dirs, files in os.walk(LIBS_DIR):
			if "miniqwen-cli.exe" in files:
				src = os.path.join(root, "miniqwen-cli.exe")
				dest_dir = os.path.join(LIBS_DIR, "bin")
				os.makedirs(dest_dir, exist_ok=True)
				dest = os.path.join(dest_dir, "miniqwen-cli.exe")
				if src != dest:
					try:
						import shutil
						shutil.copy2(src, dest)
					except Exception:
						log.exception("Failed to move miniqwen-cli.exe")
				break
