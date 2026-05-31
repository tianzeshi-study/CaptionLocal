# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2025 NV Access Limited, Tianze
# This file may be used under the terms of the GNU General Public License, version 2 or later, as modified by the NVDA license.
# For full terms and any additional permissions, see the NVDA license file: https://github.com/nvaccess/nvda/blob/master/copying.txt

import base64
import json
import requests
import io
from typing import Callable
from logHandler import log
from .base import ImageCaptioner

try:
	_
except NameError:
	_ = lambda x: x

class CustomEndpointCaptioner(ImageCaptioner):
	"""Captioner using custom OpenAI-compatible API endpoints."""

	def __init__(self, endpoint: str, api_key: str, model: str, prompt: str = None):
		"""
		Initialize the custom endpoint captioner.
		
		:param endpoint: Base URL of the API.
		:param api_key: API key.
		:param model: Model name.
		:param prompt: Custom prompt.
		"""
		self.endpoint = endpoint.rstrip('/')
		self.api_key = api_key
		self.model = model
		# Translators: default prompt for image captioning
		self.prompt = prompt or _("Please describe the picture in one sentence")

	@classmethod
	def from_config(cls, config_path: str):
		"""
		Create a CustomEndpointCaptioner from a config file.
		"""
		with open(config_path, "r", encoding="utf-8") as f:
			config = json.load(f)
		
		endpoint = config.get("endpoint")
		api_key = config.get("api_key")
		model = config.get("model")
		prompt = config.get("prompt", None)
		
		if endpoint and model:
			return cls(endpoint, api_key, model, prompt)
			
		raise ValueError(f"Invalid custom endpoint configuration in {config_path}")

	def generateCaption(
		self,
		image: str | bytes,
		maxLength: int | None = None,
		onToken: Callable[[str], None] | None = None,
	) -> str:
		"""
		Generate caption via custom endpoint.
		"""
		try:
			if isinstance(image, str):
				with open(image, "rb") as f:
					img_data = f.read()
			else:
				img_data = image
				
			base64_image = base64.b64encode(img_data).decode('utf-8')
			
			headers = {
				"Content-Type": "application/json"
			}
			if self.api_key:
				headers["Authorization"] = f"Bearer {self.api_key}"
			
			payload = {
				"model": self.model,
				"messages": [
					{
						"role": "user",
						"content": [
							{"type": "text", "text": self.prompt},
							{
								"type": "image_url",
								"image_url": {
									"url": f"data:image/jpeg;base64,{base64_image}"
								}
							}
						]
					}
				],
				"stream": bool(onToken)
			}
			
			if maxLength:
				payload["max_tokens"] = maxLength

			response = requests.post(
				f"{self.endpoint}/chat/completions",
				headers=headers,
				json=payload,
				stream=bool(onToken),
				timeout=60
			)
			response.raise_for_status()
			
			if onToken:
				full_text = ""
				for line in response.iter_lines():
					if line:
						line_str = line.decode('utf-8').strip()
						if line_str.startswith("data:"):
							data_str = line_str[len("data:"):].strip()
							if data_str == "[DONE]":
								break
							try:
								data = json.loads(data_str)
								choices = data.get('choices', [])
								if not choices:
									continue
								content = choices[0].get('delta', {}).get('content', '')
								if content:
									full_text += content
									onToken(content)
							except Exception:
								continue
				return full_text.strip()
			else:
				data = response.json()
				return data['choices'][0]['message']['content'].strip()
		except Exception as e:
			log.exception(f"Custom endpoint API request failed: {e}")
			raise
