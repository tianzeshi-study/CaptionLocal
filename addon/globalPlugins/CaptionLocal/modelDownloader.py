# -*- coding: UTF-8 -*-
"""
Multi‑threaded model downloader
==============================

Download ONNX / tokenizer assets from *Hugging Face* (or any HTTP host)
with progress callbacks.

Run this file directly for a CLI demonstration.

Example
-------
.. code:: bash

	python download_models.py  # will download to ``models`` sibling dir
"""

from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

try:
	import addonHandler
	addonHandler.initTranslation()
except:
	_ = format
	pass


_: Callable[[str], str]	 # translation alias injected by NVDA

# --------------------------------------------------------------------------- #
# Type Aliases & Constants
# --------------------------------------------------------------------------- #

# (fileName, downloadedBytes, totalBytes, progressPercent)
ProgressCallback = Callable[[str, int, int, float], None]

CHUNK_SIZE: int = 8_192
MAX_RETRIES: int = 3
BACKOFF_BASE: int = 2


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def ensureModelsDirectory(basePath: str | None = None) -> str:
	"""
	Ensure the *models* directory exists (``../../models`` relative to *basePath*).

	:param basePath: Base folder; defaults to the directory containing *this* file.
	:return: Absolute path of the *models* directory.
	:raises OSError: When the directory cannot be created.
	"""
	here = basePath or os.path.dirname(__file__)
	modelsDir = os.path.abspath(os.path.join(here, "..", "..", "models"))

	try:
		Path(modelsDir).mkdir(parents=True, exist_ok=True)
		# Translators: Logged when the local models directory is created / found.
		_(f"Models directory ensured:{modelsDir} ")
		return modelsDir
	except OSError as err:
		raise OSError(f"Failed to create models directory {modelsDir}: {err}") from err


def constructDownloadUrl(
	remoteHost: str,
	modelName: str,
	filePath: str,
	resolvePath: str = "/resolve/main",
) -> str:
	"""
	Construct a full download URL for *Hugging Face‑style* repositories.

	:param remoteHost: ``huggingface.co`` or other HTTP(S) host.
	:param modelName: Model repository name, e.g. ``Xenova/vit-gpt2-image-captioning``.
	:param filePath: Path inside the repo.
	:param resolvePath: The branch / ref path, default ``/resolve/main``.
	"""
	if not remoteHost.startswith(("http://", "https://")):
		remoteHost = f"https://{remoteHost}"

	base = remoteHost.rstrip("/")
	model = modelName.strip("/")
	ref = resolvePath.strip("/")
	filePath = filePath.lstrip("/")

	return f"{base}/{model}/{ref}/{filePath}"


def downloadSingleFile(
	url: str,
	localPath: str,
	maxRetries: int = MAX_RETRIES,
	progressCallback: ProgressCallback | None = None,
) -> tuple[bool, str]:
	"""
	Download a single file with basic exponential back‑off retry strategy.

	:param url: Remote URL.
	:param localPath: Destination path.
	:param maxRetries: Attempt count before failing.
	:param progressCallback: Optional progress reporter.
	:return: ``(success, message)``
	"""
	threadId = threading.current_thread().ident or 0
	fileName = os.path.basename(localPath)

	# Create destination directory
	try:
		Path(os.path.dirname(localPath)).mkdir(parents=True, exist_ok=True)
	except OSError as err:
		return False, f"Failed to create directory {localPath}: {err}"

	# Skip if already present
	if os.path.exists(localPath):
		if progressCallback:
			size = os.path.getsize(localPath)
			progressCallback(fileName, size, size, 100.0)
		# Translators: Logged when download is skipped because the file exists.
		_("[Thread-{threadId}] File already exists:	 {localPath}")
		return True, f"File already exists: {localPath}"

	for attempt in range(maxRetries):
		try:
			# Translators: Logged at the start of each download attempt.
			print(
				_(f"[Thread-{threadId}] Downloading (attempt {attempt + 1}/{maxRetries}): {url}")
			)

			req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
			with urllib.request.urlopen(req, timeout=30) as resp:
				total = int(resp.headers.get("Content-Length", "0"))
				if total:
					# Translators: Logged once file size is known.
					print(
						_("[Thread-{id}] File size: {size:,} bytes").format(
							id=threadId, size=total
						)
					)

				downloaded = 0
				lastReported = 0

				with open(localPath, "wb") as fh:
					while True:
						chunk = resp.read(CHUNK_SIZE)
						if not chunk:
							break
						fh.write(chunk)
						downloaded += len(chunk)

						if progressCallback and total:
							percent = downloaded / total * 100
							if (
								downloaded - lastReported >= 1_048_576	# 1 MiB
								or abs(percent - lastReported / total * 100) >= 1.0
								or downloaded == total
							):
								progressCallback(
									fileName, downloaded, total, percent
								)
								lastReported = downloaded

				if progressCallback and total:
					progressCallback(fileName, downloaded, total, 100.0)

			# Verify
			if os.path.getsize(localPath) > 0:
				# Translators: Logged when a file finishes downloading.
				print(
					_("[Thread-{id}] Successfully downloaded: ").format(id=threadId)
					+ localPath
				)
				return True, "Download completed"
			raise RuntimeError("Downloaded file is empty")

		except urllib.error.HTTPError as err:
			msg = f"HTTP {err.code}: {err.reason}"
		except urllib.error.URLError as err:
			msg = f"URL Error: {err.reason}"
		except Exception as err:  # noqa: BLE001
			msg = f"Unexpected error: {err}"
		# Failure handling / retry
		print(f"[Thread-{threadId}] {msg} – {url}")
		if attempt < maxRetries - 1:
			wait = BACKOFF_BASE**attempt
			print(f"[Thread-{threadId}] Waiting {wait}s before retry…")
			time.sleep(wait)
		else:
			return False, msg
	return False, "Unreachable"


def downloadModelsMultithreaded(
	modelsDir: str,
	remoteHost: str = "huggingface.co",
	modelName: str = "Xenova/vit-gpt2-image-captioning",
	filesToDownload: list[str] | None = None,
	resolvePath: str = "/resolve/main",
	maxWorkers: int = 4,
	progressCallback: ProgressCallback | None = None,
) -> tuple[list[str], list[str]]:
	"""
	Download multiple model assets concurrently.

	:param modelsDir: Base *models* directory.
	:param remoteHost: Hostname (default ``huggingface.co``).
	:param modelName: Repository name.
	:param filesToDownload: Explicit file list; *None* uses common defaults.
	:param resolvePath: Branch / ref path.
	:param maxWorkers: Thread pool size.
	:param progressCallback: Optional reporter.
	:return: ``(successfulPaths, failedPaths)``
	"""
	if not remoteHost or not modelName:
		raise ValueError("remoteHost and modelName cannot be empty")

	filesToDownload = filesToDownload or [
		"onnx/encoder_model_quantized.onnx",
		"onnx/decoder_model_merged_quantized.onnx",
		"config.json",
		"vocab.json",
	]
	if not filesToDownload:
		raise ValueError("filesToDownload cannot be empty")


	print(_(f"Starting download of {len(filesToDownload)} files for model: {modelName}\nRemote host: {remoteHost}\nMax workers: {maxWorkers}"))
	

	localModelDir = os.path.join(modelsDir, modelName)
	successful: list[str] = []
	failed: list[str] = []

	with ThreadPoolExecutor(max_workers=maxWorkers) as executor:
		taskMap = {
			executor.submit(
				downloadSingleFile,
				constructDownloadUrl(remoteHost, modelName, path, resolvePath),
				os.path.join(localModelDir, path),
				MAX_RETRIES,
				progressCallback,
			): path
			for path in filesToDownload
		}

		for future in as_completed(taskMap):
			filePath = taskMap[future]
			try:
				ok, _msg = future.result()
				if ok:
					successful.append(filePath)
					print("✓ " + filePath)
				else:
					failed.append(filePath)
					print("✗ " + filePath)
			except Exception as err:  # noqa: BLE001
				failed.append(filePath)
				print(f"✗ {filePath} – {err}")

	# Summary
	print("\n=== Download Summary ===")
	print(f"Total: {len(filesToDownload)}")
	print(f"Successful: {len(successful)}")
	print(f"Failed: {len(failed)}")
	print(f"\nLocal model directory: {localModelDir}")

	return successful, failed


def getModelFilePaths(
	modelName: str = "Xenova/vit-gpt2-image-captioning",
	basePath: str | None = None,
) -> dict[str, str]:
	"""
	Return absolute paths for encoder / decoder / config / vocab.

	:param modelName: Repository name.
	:param basePath: Base folder for *models*.
	"""
	modelsDir = ensureModelsDirectory(basePath)
	local = os.path.join(modelsDir, modelName)
	return {
		"encoderPath": os.path.join(local, "onnx", "encoder_model_quantized.onnx"),
		"decoderPath": os.path.join(local, "onnx", "decoder_model_merged_quantized.onnx"),
		"configPath": os.path.join(local, "config.json"),
		"vocabPath": os.path.join(local, "vocab.json"),
		"modelDir": local,
	}


# --------------------------------------------------------------------------- #
# CLI Demo
# --------------------------------------------------------------------------- #


def _exampleProgress(fileName: str, done: int, total: int, pct: float) -> None:
	"""
	Simple CLI progress reporter.
	"""
	print(f"[PROGRESS] {fileName}: {pct:5.1f}% ({done:,}/{total:,} B)")


def main() -> None:	 # pragma: no cover – CLI only
	"""
	Download the default model when executed as a script.
	"""
	modelsDir = ensureModelsDirectory()
	ok, failed = downloadModelsMultithreaded(
		modelsDir=modelsDir,
		progressCallback=_exampleProgress,
	)
	if not failed:
		print("\n🎉	All files downloaded successfully!")
		for k, v in getModelFilePaths().items():
			print(f"{k}: {v}")
	else:
		print("\n⚠️	 Some files failed to download:", failed)


if __name__ == "__main__":
	main()
