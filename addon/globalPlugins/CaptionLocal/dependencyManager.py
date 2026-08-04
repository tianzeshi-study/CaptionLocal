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
import re
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
		
		# For others, check if the package directory exists
		norm_name = runtime_id.replace("-", "_").lower()
		return os.path.exists(os.path.join(LIBS_DIR, norm_name))

	def download_and_install(self, runtime_id: str, progress_callback: Optional[ProgressCallback] = None) -> bool:
		"""Download and install a runtime dependency."""
		info = self.runtimes.get(runtime_id)
		if not info:
			log.error(f"Unknown runtime: {runtime_id}")
			return False

		if info.get("type") == "pypi":
			package_spec = info.get("package", runtime_id)
			version = info.get("version")
			py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
			if "versions" in info:
				version = info["versions"].get(py_ver, version)
			
			self.installed_in_session = set()
			return self._install_package(package_spec, version, progress_callback)
		
		return False

	def _install_package(self, package_spec: str, version: Optional[str] = None, progress_callback: Optional[ProgressCallback] = None) -> bool:
		# Parse name and extras
		match = re.match(r"^([a-zA-Z0-9._-]+)(?:\[([a-zA-Z0-9._,-]+)\])?.*", package_spec)
		if not match:
			return False
		package_name = match.group(1)
		extras = match.group(2).split(",") if match.group(2) else []
		
		if package_name.lower() in self.installed_in_session:
			return True
		self.installed_in_session.add(package_name.lower())

		try:
			# 1. Fetch metadata from PyPI
			url = f"https://pypi.org/pypi/{package_name}/json"
			if version:
				url = f"https://pypi.org/pypi/{package_name}/{version}/json"
			
			resp = requests.get(url, timeout=10)
			resp.raise_for_status()
			data = resp.json()
			
			# 2. Find best matching wheel
			releases = data.get("urls", [])
			best_url = None
			best_score = -1
			filename_matched = ""
			file_size = 0
			
			curr_py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
			
			for release in releases:
				filename = release.get("filename", "")
				if not filename.endswith(".whl"):
					continue
				
				try:
					tags_part = filename[:-4].rsplit("-", 3)
					if len(tags_part) < 3:
						continue
					f_py, f_abi, f_plat = tags_part[-3], tags_part[-2], tags_part[-1]
					
					p_score = -1
					if f_plat == "win_amd64":
						p_score = 2
					elif f_plat == "any":
						p_score = 1
					
					if p_score == -1:
						continue
					
					py_score = -1
					if curr_py_tag in f_py:
						py_score = 2
					elif f_py == "py3" or f_py == "py3-none":
						py_score = 1
					
					if py_score == -1:
						continue
					
					score = p_score * 10 + py_score
					if score > best_score:
						best_score = score
						best_url = release.get("url")
						file_size = release.get("size", 0)
						filename_matched = filename
						if score == 22: break
				except Exception:
					continue
			
			if not best_url:
				log.error(f"No compatible wheel for {package_name}")
				return False

			# 3. Download and Unzip
			if progress_callback:
				progress_callback(filename_matched, 0, file_size, 0.0)

			download_resp = requests.get(best_url, stream=True, timeout=30)
			download_resp.raise_for_status()
			
			content = io.BytesIO()
			downloaded = 0
			for chunk in download_resp.iter_content(chunk_size=8192):
				if chunk:
					content.write(chunk)
					downloaded += len(chunk)
					if progress_callback:
						progress_callback(filename_matched, downloaded, file_size, (downloaded/file_size)*100 if file_size else 0)

			content.seek(0)
			if progress_callback:
				progress_callback(f"[EXTRACTING]{filename_matched}", file_size, file_size, 100.0)

			os.makedirs(LIBS_DIR, exist_ok=True)
			with zipfile.ZipFile(content) as zf:
				zf.extractall(LIBS_DIR)

			if LIBS_DIR not in sys.path:
				sys.path.insert(0, LIBS_DIR)
			
			# 4. Handle dependencies
			requires = data.get("info", {}).get("requires_dist", [])
			if requires:
				for req in requires:
					# Simple marker evaluation
					if ";" in req:
						dep_spec, marker = req.split(";", 1)
						dep_spec = dep_spec.strip()
						marker = marker.strip()
						
						# Check for extra and platform
						keep = True
						if "extra ==" in marker:
							m_extra = re.search(r"extra == ['\"]([^'\"]+)['\"]", marker)
							if m_extra and m_extra.group(1) not in extras:
								keep = False
						if "sys_platform ==" in marker:
							if "win32" not in marker:
								keep = False
						
						if not keep:
							continue
					else:
						dep_spec = req.strip()
					
					# Recursive install
					self._install_package(dep_spec, progress_callback=progress_callback)

			# 5. Post-install fixes
			if package_name.lower() == "miniqinference" or "miniqinference" in package_spec.lower():
				self._fix_miniqinference_paths()

			return True

		except Exception:
			log.exception(f"Failed to install {package_spec}")
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
