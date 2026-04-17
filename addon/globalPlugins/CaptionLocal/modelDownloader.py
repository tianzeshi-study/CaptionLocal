# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2025 NV Access Limited, Tianze
# This file may be used under the terms of the GNU General Public License, version 2 or later, as modified by the NVDA license.
# For full terms and any additional permissions, see the NVDA license file: https://github.com/nvaccess/nvda/blob/master/copying.txt

"""
Multi‑threaded model downloader
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, List, Tuple, Optional, Set

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from requests.models import Response
from urllib3.util.retry import Retry

from logHandler import log
import config

# Type definitions
ProgressCallback = Callable[[str, int, int, float], None]

# Constants
CHUNK_SIZE: int = 8_192
MAX_RETRIES: int = 3
BACKOFF_BASE: int = 2  # Base delay (in seconds) for exponential backoff strategy


class ModelDownloader:
	"""Multi-threaded model downloader with progress tracking and retry logic."""

	def __init__(
		self,
		remoteHost: str = "huggingface.co",
		maxWorkers: int = 4,
		maxRetries: int = MAX_RETRIES,
	):
		"""
		Initialize the ModelDownloader.
		"""
		self.remoteHost = remoteHost
		self.maxWorkers = maxWorkers
		self.maxRetries = maxRetries

		# Thread control
		self.cancelRequested = False
		self.downloadLock = threading.Lock()
		self.activeFutures: Set = set()

		# Configure requests session with retry strategy and automatic redirects
		self.session = requests.Session()

		# Configure retry strategy
		retryStrategy = Retry(
			total=maxRetries,
			backoff_factor=BACKOFF_BASE,
			status_forcelist=[429, 500, 502, 503, 504],
			allowed_methods=["HEAD", "GET", "OPTIONS"],
		)

		adapter = HTTPAdapter(max_retries=retryStrategy)
		self.session.mount("https://", adapter)

	def requestCancel(self) -> None:
		"""Request cancellation of all active downloads."""
		log.debug("Cancellation requested")
		self.cancelRequested = True

		# Cancel all active futures
		with self.downloadLock:
			for future in self.activeFutures:
				if not future.done():
					future.cancel()
			self.activeFutures.clear()

	def resetCancellation(self) -> None:
		"""Reset cancellation state for new download session."""
		with self.downloadLock:
			self.cancelRequested = False
			self.activeFutures.clear()

	def ensureModelsDirectory(self, defaultPath: str) -> str:
		"""
		Ensure the *models* directory exists.
		"""
		modelsDir = os.path.abspath(defaultPath)

		try:
			Path(modelsDir).mkdir(parents=True, exist_ok=True)
		except OSError as err:
			raise OSError(f"Failed to create models directory {modelsDir}: {err}") from err
		else:
			log.debug(f"Models directory ensured: {modelsDir}")
			return modelsDir

	def constructDownloadUrl(
		self,
		modelName: str,
		filePath: str,
		resolvePath: str = "/resolve/main",
	) -> str:
		"""
		Construct a full download URL for *Hugging Face‑style* repositories.
		"""
		remoteHost = self.remoteHost
		if not remoteHost.startswith(("http://", "https://")):
			remoteHost = f"https://{remoteHost}"

		base = remoteHost.rstrip("/")
		model = modelName.strip("/")
		ref = resolvePath.strip("/")
		filePath = filePath.lstrip("/")

		return f"{base}/{model}/{ref}/{filePath}"

	def _getRemoteFileSize(self, url: str) -> int:
		"""
		Get remote file size using HEAD request.
		"""
		if self.cancelRequested:
			return 0

		try:
			response = self.session.head(url, timeout=10, allow_redirects=True)
			response.raise_for_status()
		except Exception as e:
			if not self.cancelRequested:
				log.warning(f"Failed to get remote file size (HEAD) for {url}: {e}")
		else:
			contentLength = response.headers.get("Content-Length")
			if contentLength:
				return int(contentLength)

		try:
			response = self.session.get(url, headers={"Range": "bytes=0-0"}, timeout=10, allow_redirects=True)
		except Exception as e:
			if not self.cancelRequested:
				log.warning(f"Failed to get remote file size (GET) for {url}: {e}")
		else:
			if response.status_code == 206:  # Partial content
				contentRange = response.headers.get("Content-Range", "")
				if contentRange and "/" in contentRange:
					return int(contentRange.split("/")[-1])

		return 0

	def _reportProgress(
		self,
		callback: ProgressCallback | None,
		fileName: str,
		downloaded: int,
		total: int,
		lastReported: int,
	) -> int:
		"""
		Report download progress.
		"""
		if not callback or total == 0 or self.cancelRequested:
			return lastReported

		percent = downloaded / total * 100

		if (
			downloaded - lastReported >= 1_048_576  # 1 MiB
			or abs(percent - lastReported / total * 100) >= 1.0
			or downloaded == total
		):
			callback(fileName, downloaded, total, percent)
			return downloaded

		return lastReported

	def downloadSingleFile(
		self,
		url: str,
		localPath: str,
		progressCallback: ProgressCallback | None = None,
	) -> Tuple[bool, str]:
		"""
		Download a single file with resume support.
		"""
		if self.cancelRequested:
			return False, "Download cancelled"

		threadId = threading.current_thread().ident or 0
		fileName = os.path.basename(localPath)

		# Create destination directory
		success, message = self._createDestinationDirectory(localPath)
		if not success:
			return False, message

		# Get remote file size
		remoteSize = self._getRemoteFileSize(url)

		if self.cancelRequested:
			return False, "Download cancelled"

		# Check if file already exists and is complete
		success, message = self._checkExistingFile(
			localPath,
			remoteSize,
			fileName,
			progressCallback,
			threadId,
		)
		if success is not None:
			return success, message

		# Attempt download with retries
		return self._downloadWithRetries(url, localPath, fileName, threadId, progressCallback)

	def _createDestinationDirectory(self, localPath: str) -> Tuple[bool, str]:
		"""Create destination directory if it doesn't exist."""
		try:
			Path(os.path.dirname(localPath)).mkdir(parents=True, exist_ok=True)
			return True, ""
		except OSError as err:
			return False, f"Failed to create directory {localPath}: {err}"

	def _checkExistingFile(
		self,
		localPath: str,
		remoteSize: int,
		fileName: str,
		progressCallback: ProgressCallback | None,
		threadId: int,
	) -> Tuple[Optional[bool], str]:
		"""Check if file already exists and is complete."""
		if not os.path.exists(localPath):
			return None, ""

		localSize = os.path.getsize(localPath)

		if remoteSize > 0:
			if localSize == remoteSize:
				if progressCallback and not self.cancelRequested:
					progressCallback(fileName, localSize, localSize, 100.0)
				return True, f"File already complete: {localPath}"
			elif localSize > remoteSize:
				try:
					os.remove(localPath)
				except OSError:
					pass
		else:
			if localSize > 0:
				if progressCallback and not self.cancelRequested:
					progressCallback(fileName, localSize, localSize, 100.0)
				return True, f"File already exists: {localPath}"

		return None, ""

	def _downloadWithRetries(
		self,
		url: str,
		localPath: str,
		fileName: str,
		threadId: int,
		progressCallback: ProgressCallback | None,
	) -> Tuple[bool, str]:
		"""Attempt download with retry logic."""
		for attempt in range(self.maxRetries):
			if self.cancelRequested:
				return False, "Download cancelled"

			try:
				success, message = self._performSingleDownload(
					url,
					localPath,
					fileName,
					threadId,
					progressCallback,
				)

			except requests.exceptions.HTTPError as e:
				message = self._handleHttpError(e, localPath, fileName, progressCallback, threadId)
				if message.startswith("Download completed"):
					return True, message

			except RequestException as e:
				if self.cancelRequested:
					return False, "Download cancelled"
				message = f"Request error: {str(e)}"

			except Exception as e:
				if self.cancelRequested:
					return False, "Download cancelled"
				message = f"Unexpected error: {str(e)}"
				log.error(message)

			else:
				if success:
					return True, message

			if not self.cancelRequested:
				if attempt < self.maxRetries - 1:
					success = self._waitForRetry(attempt, threadId)
					if not success:
						return False, "Download cancelled"
				else:
					return False, message

		return False, "Maximum retries exceeded"

	def _performSingleDownload(
		self,
		url: str,
		localPath: str,
		fileName: str,
		threadId: int,
		progressCallback: ProgressCallback | None,
	) -> Tuple[bool, str]:
		"""Perform a single download attempt with resume support."""
		resumePos = 0
		if os.path.exists(localPath):
			resumePos = os.path.getsize(localPath)

		# Set up headers for resume
		headers = {}
		if resumePos > 0:
			headers["Range"] = f"bytes={resumePos}-"

		# Make request
		response = self.session.get(
			url,
			headers=headers,
			stream=True,
			timeout=10,
			allow_redirects=True,
		)

		# Check if resume is supported
		if resumePos > 0 and response.status_code != 206:
			if os.path.exists(localPath):
				try:
					os.remove(localPath)
				except OSError:
					pass

			if self.cancelRequested:
				response.close()
				raise Exception("Download cancelled")

			response.close()
			response = self.session.get(url, stream=True, timeout=10, allow_redirects=True)

		response.raise_for_status()

		if self.cancelRequested:
			response.close()
			return False, "Download cancelled"

		try:
			# Determine total file size
			if response.status_code == 206:
				contentRange = response.headers.get("Content-Range", "")
				if contentRange and "/" in contentRange:
					total = int(contentRange.split("/")[-1])
				else:
					total = int(response.headers.get("Content-Length", "0")) + resumePos
			else:
				total = int(response.headers.get("Content-Length", "0"))

			downloaded = resumePos
			lastReported = downloaded
			mode = "ab" if resumePos > 0 else "wb"

			with open(localPath, mode) as fh:
				for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
					if self.cancelRequested:
						return False, "Download cancelled"

					if chunk:
						fh.write(chunk)
						downloaded += len(chunk)

						if total > 0:
							lastReported = self._reportProgress(
								progressCallback,
								fileName,
								downloaded,
								total,
								lastReported,
							)

			# Verify
			actualSize = os.path.getsize(localPath)
			if actualSize == 0:
				return False, "Downloaded file is empty"
			if total > 0 and actualSize != total:
				return False, f"File incomplete: {actualSize}/{total} bytes"

			if progressCallback and not self.cancelRequested:
				progressCallback(fileName, actualSize, max(total, actualSize), 100.0)

			return True, "Download completed"

		finally:
			response.close()

	def _handleHttpError(
		self,
		error: requests.exceptions.HTTPError,
		localPath: str,
		fileName: str,
		progressCallback: ProgressCallback | None,
		threadId: int,
	) -> str:
		"""Handle HTTP errors."""
		if error.response is not None and error.response.status_code == 416:  # Range Not Satisfiable
			if os.path.exists(localPath):
				actualSize = os.path.getsize(localPath)
				if actualSize > 0:
					if progressCallback and not self.cancelRequested:
						progressCallback(fileName, actualSize, actualSize, 100.0)
					return "Download completed"
		return f"HTTP {error.response.status_code if error.response else 'Error'}: {str(error)}"

	def _waitForRetry(self, attempt: int, threadId: int) -> bool:
		"""Wait for retry."""
		wait = BACKOFF_BASE**attempt
		for _ in range(wait):
			if self.cancelRequested:
				return False
			time.sleep(1)
		return True

	def downloadModelsMultithreaded(
		self,
		modelsDir: str,
		modelName: str = "Xenova/vit-gpt2-image-captioning",
		filesToDownload: Optional[List[str]] = None,
		resolvePath: str = "/resolve/main",
		progressCallback: Optional[ProgressCallback] = None,
		maxWorkers: int = 4
	) -> Tuple[List[str], List[str]]:
		"""Download multiple model assets concurrently."""
		if not self.remoteHost or not modelName:
			raise ValueError("remoteHost and modelName cannot be empty")

		filesToDownload = filesToDownload or [
			"onnx/encoder_model_quantized.onnx",
			"onnx/decoder_model_merged_quantized.onnx",
			"config.json",
			"vocab.json",
			"preprocessor_config.json",
		]

		localModelDir = os.path.join(modelsDir, modelName)
		successful: List[str] = []
		failed: List[str] = []

		with ThreadPoolExecutor(max_workers=maxWorkers) as executor:
			futures = []

			for path in filesToDownload:
				if self.cancelRequested:
					break

				future = executor.submit(
					self.downloadSingleFile,
					self.constructDownloadUrl(modelName, path, resolvePath),
					os.path.join(localModelDir, path),
					progressCallback,
				)
				futures.append((future, path))

				with self.downloadLock:
					self.activeFutures.add(future)

			for future, filePath in futures:
				if self.cancelRequested:
					break

				with self.downloadLock:
					self.activeFutures.discard(future)

				try:
					ok, msg = future.result()
					if ok:
						successful.append(filePath)
					else:
						failed.append(filePath)
				except Exception:
					failed.append(filePath)

		return successful, failed

	def __del__(self):
		if hasattr(self, "session"):
			self.session.close()

# For backward compatibility
def downloadModelsMultithreaded(*args, **kwargs):
	downloader = ModelDownloader(remoteHost=kwargs.get('remoteHost', 'huggingface.co'))
	# remove remoteHost from kwargs if present to avoid duplicate
	if 'remoteHost' in kwargs:
		del kwargs['remoteHost']
	return downloader.downloadModelsMultithreaded(*args, **kwargs)

def ensureModelsDirectory(defaultPath: str) -> str:
	downloader = ModelDownloader()
	return downloader.ensureModelsDirectory(defaultPath)
