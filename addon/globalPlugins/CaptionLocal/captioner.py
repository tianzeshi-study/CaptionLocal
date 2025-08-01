# -*- coding: UTF-8 -*-
"""Lightweight ONNX Runtime Image Captioning Model.

This module provides a lightweight image captioning solution using ONNX Runtime
without PyTorch dependencies. It supports Vision Transformer (ViT) encoder and
GPT-2 decoder models for generating descriptive captions from images.
"""

from __future__ import unicode_literals

import os
import sys
import json
import re
import io
import time
from typing import List, Dict

# Add libs directory to path
_here = os.path.dirname(__file__)
_libsDir = os.path.join(_here, "libs")
sys.path.insert(0, _libsDir)
import numpy as np
from PIL import Image
import onnxruntime as ort



class ImageCaptioner:
	"""Lightweight ONNX Runtime image captioning model.
	
	This class provides image captioning functionality using ONNX models
	without PyTorch dependencies. It uses a Vision Transformer encoder
	and GPT-2 decoder for generating captions.
	"""

	def __init__(self, encoder_path: str, decoder_path: str, config_path: str, 
				 enableProfiling: bool = False) -> None:
		"""Initialize the lightweight ONNX image captioning model.

		Args:
			encoder_path: Path to the ViT encoder ONNX model.
			decoder_path: Path to the GPT-2 decoder ONNX model.
			config_path: Path to the configuration file (required).
			enableProfiling: Whether to enable ONNX Runtime profiling.
			
		Raises:
			FileNotFoundError: If config file is not found.
			Exception: If model initialization fails.
		"""
		# Load configuration file
		try:
			with open(config_path, 'r', encoding='utf-8') as f:
				self.config = json.load(f)
		except FileNotFoundError:
			raise FileNotFoundError(
				f"Caption model config file {config_path} not found, "
				"please download models and config file first!"
			)
		except Exception as e:
			print(e)
			raise

		# Load vocabulary from vocab.json in the same directory as config
		configDir = os.path.dirname(config_path)
		vocabPath = os.path.join(configDir, 'vocab.json')
		self.vocab = self._loadVocab(vocabPath)
		self.vocabSize = len(self.vocab)

		# Load all model parameters from configuration
		self._loadModelParams()

		# Configure ONNX Runtime session
		sessionOptions = ort.SessionOptions()
		if enableProfiling:
			sessionOptions.enable_profiling = True

		# Load ONNX models
		self.encoderSession = ort.InferenceSession(encoder_path, sess_options=sessionOptions)
		self.decoderSession = ort.InferenceSession(decoder_path, sess_options=sessionOptions)

		print(f"Loaded ONNX models - Encoder: {encoder_path}, Decoder: {decoder_path}")
		print(f"Loaded config from: {config_path}")
		print(f"Loaded vocabulary from: {vocabPath}")
		print(f"Model config - Image size: {self.imageSize}, Max length: {self.maxLength}")

	def _loadModelParams(self) -> None:
		"""Load all model parameters from configuration file."""
		# Encoder parameters
		encoderConfig = self.config.get('encoder', {})
		self.imageSize = encoderConfig.get('image_size', 224)
		self.numChannels = encoderConfig.get('num_channels', 3)
		self.patchSize = encoderConfig.get('patch_size', 16)
		self.encoderHiddenSize = encoderConfig.get('hidden_size', 768)
		self.encoderNumLayers = encoderConfig.get('num_hidden_layers', 12)
		self.encoderNumHeads = encoderConfig.get('num_attention_heads', 12)
		self.encoderIntermediateSize = encoderConfig.get('intermediate_size', 3072)

		# Decoder parameters
		decoderConfig = self.config.get('decoder', {})
		self.maxLength = decoderConfig.get('max_length', 20)
		self.decoderVocabSize = decoderConfig.get('vocab_size', 50257)
		self.nEmbd = decoderConfig.get('n_embd', 768)
		self.nLayer = decoderConfig.get('n_layer', 12)
		self.nHead = decoderConfig.get('n_head', 12)
		self.nCtx = decoderConfig.get('n_ctx', 1024)
		self.nPositions = decoderConfig.get('n_positions', 1024)

		# Special token IDs
		self.bosTokenId = self.config.get('bos_token_id', 50256)
		self.eosTokenId = self.config.get('eos_token_id', 50256)
		self.padTokenId = self.config.get('pad_token_id', 50256)

		# Generation parameters
		generationConfig = self.config.get('generation', {})
		self.doSample = generationConfig.get('do_sample', False)
		self.numBeams = generationConfig.get('num_beams', 1)
		self.temperature = generationConfig.get('temperature', 1.0)
		self.topK = generationConfig.get('top_k', 50)
		self.topP = generationConfig.get('top_p', 1.0)
		self.repetitionPenalty = generationConfig.get('repetition_penalty', 1.0)
		self.lengthPenalty = generationConfig.get('length_penalty', 1.0)

	def _loadVocab(self, vocabPath: str) -> Dict[int, str]:
		"""Load vocabulary file.

		Args:
			vocabPath: Path to vocab.json file.

		Returns:
			Dictionary mapping token IDs to tokens.
		"""
		try:
			with open(vocabPath, 'r', encoding='utf-8') as f:
				vocabData = json.load(f)

			# Convert to id -> token format
			vocab = {v: k for k, v in vocabData.items()}
			print(f"Successfully loaded vocabulary with {len(vocab)} tokens")
			return vocab

		except FileNotFoundError:
			print(f"Warning: vocab.json not found at {vocabPath}")
			print("Using fallback vocabulary")
			return self._getFallbackVocab()
		except Exception as e:
			print(f"Warning: Could not load vocabulary from {vocabPath}: {e}")
			print("Using fallback vocabulary")
			return self._getFallbackVocab()

	def _getFallbackVocab(self) -> Dict[int, str]:
		"""Build a simplified fallback vocabulary.
		
		Returns:
			Dictionary with basic vocabulary for fallback use.
		"""
		# Basic special tokens
		vocab = {
			50256: '<|endoftext|>',  # BOS/EOS/PAD token
			50257: '<|pad|>',
		}

		# Common words (example set - would need complete vocabulary in practice)
		commonWords = [
			"a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
			"man", "woman", "person", "people", "child", "children", "boy", "girl", "dog", "cat",
			"car", "truck", "bus", "bike", "motorcycle", "train", "plane", "boat", "house", "building",
			"tree", "flower", "grass", "sky", "cloud", "sun", "moon", "water", "river", "ocean",
			"red", "blue", "green", "yellow", "black", "white", "brown", "orange", "purple", "pink",
			"big", "small", "tall", "short", "old", "young", "new", "beautiful", "ugly", "good", "bad",
			"sitting", "standing", "walking", "running", "eating", "drinking", "playing", "working",
			"is", "are", "was", "were", "has", "have", "had", "will", "would", "could", "should",
			"very", "quite", "really", "too", "also", "just", "only", "even", "still", "already"
		]

		# Add common words to vocabulary
		for i, word in enumerate(commonWords):
			if i < 50256:  # Avoid conflicts with special tokens
				vocab[i] = word

		print(f"Built fallback vocabulary with {len(vocab)} tokens")
		return vocab

	def preprocessImage(self, image: str| bytes) -> np.ndarray:
		"""Preprocess image for model input.

		Args:
			image: Image file path or binary data.

		Returns:
			Preprocessed image array ready for model input.
		"""
		if isinstance(image, str):
			img = Image.open(image).convert('RGB')
		else:
			img = Image.open(io.BytesIO(image)).convert('RGB')

		# Resize image
		img = img.resize((self.imageSize, self.imageSize), Image.LANCZOS)

		# Convert to numpy array and normalize to [0, 1]
		imgArray = np.array(img).astype(np.float32) / 255.0

		# ImageNet normalization
		mean = np.array([0.485, 0.456, 0.406])
		std = np.array([0.229, 0.224, 0.225])
		imgArray = (imgArray - mean) / std

		# Adjust dimensions: (H, W, C) -> (1, C, H, W)
		imgArray = np.transpose(imgArray, (2, 0, 1))
		imgArray = np.expand_dims(imgArray, axis=0)

		return imgArray

	def encodeImage(self, imageArray: np.ndarray) -> np.ndarray:
		"""Encode image using ViT encoder.

		Args:
			imageArray: Preprocessed image array.

		Returns:
			Encoder hidden states.
		"""
		# Get encoder input name
		inputName = self.encoderSession.get_inputs()[0].name

		# Run encoder inference
		imageArray = imageArray.astype(np.float32)
		encoderOutputs = self.encoderSession.run(None, {inputName: imageArray})

		# Return last hidden state
		return encoderOutputs[0]

	def decodeTokens(self, tokenIds: List[int]) -> str:
		"""Decode token IDs to text.

		Args:
			tokenIds: List of token IDs.

		Returns:
			Decoded text string.
		"""
		tokens = []
		for tokenId in tokenIds:
			if tokenId in self.vocab:
				token = self.vocab[tokenId]
				if token not in ['<|endoftext|>', '<|pad|>']:
					tokens.append(token)

		# Simple text post-processing
		text = ' '.join(tokens).replace("Ġ", " ")

		# Basic text cleaning
		text = re.sub(r'\s+', ' ', text)  # Merge multiple spaces
		text = text.strip()

		return text

	def getDecoderInputNames(self) -> List[str]:
		"""Get decoder input names for debugging.
		
		Returns:
			List of decoder input names.
		"""
		return [inp.name for inp in self.decoderSession.get_inputs()]

	def getDecoderOutputNames(self) -> List[str]:
		"""Get decoder output names for debugging.
		
		Returns:
			List of decoder output names.
		"""
		return [out.name for out in self.decoderSession.get_outputs()]

	def printModelInfo(self) -> None:
		"""Print model information for debugging."""
		print("=== Encoder Model Info ===")
		for i, inp in enumerate(self.encoderSession.get_inputs()):
			print(f"Input {i}: {inp.name}, shape: {inp.shape}, type: {inp.type}")
		for i, out in enumerate(self.encoderSession.get_outputs()):
			print(f"Output {i}: {out.name}, shape: {out.shape}, type: {out.type}")

		print("\n=== Decoder Model Info ===")
		for i, inp in enumerate(self.decoderSession.get_inputs()):
			print(f"Input {i}: {inp.name}, shape: {inp.shape}, type: {inp.type}")
		for i, out in enumerate(self.decoderSession.get_outputs()):
			print(f"Output {i}: {out.name}, shape: {out.shape}, type: {out.type}")

	def _initializePastKeyValues(self, batchSize: int = 1) -> Dict[str, np.ndarray]:
		"""Initialize past_key_values for decoder.

		Args:
			batchSize: Batch size for inference.

		Returns:
			Dictionary of initialized past key values.
		"""
		pastKeyValues = {}

		# Create key and value for each layer
		for layerIdx in range(self.nLayer):
			# Key and value shape: (batch_size, num_heads, 0, head_dim)
			# Initial sequence length is 0
			headDim = self.nEmbd // self.nHead

			keyShape = (batchSize, self.nHead, 0, headDim)
			valueShape = (batchSize, self.nHead, 0, headDim)

			pastKeyValues[f'past_key_values.{layerIdx}.key'] = np.zeros(keyShape, dtype=np.float32)
			pastKeyValues[f'past_key_values.{layerIdx}.value'] = np.zeros(valueShape, dtype=np.float32)

		return pastKeyValues

	def generateWithGreedy(self, encoderHiddenStates: np.ndarray, 
						   maxLength: int |None = None) -> str:
		"""Generate text using greedy search.

		Args:
			encoderHiddenStates: Encoder hidden states.
			maxLength: Maximum generation length.

		Returns:
			Generated text string.
		"""
		if maxLength is None:
			maxLength = self.maxLength

		# Initialize input sequence
		inputIds = np.array([[self.bosTokenId]], dtype=np.int64)
		generatedTokens = []

		# Initialize past_key_values
		pastKeyValues = self._initializePastKeyValues(batchSize=1)

		for step in range(maxLength):
			# Prepare decoder inputs
			decoderInputs = {
				'input_ids': inputIds if step == 0 else np.array([[generatedTokens[-1]]], dtype=np.int64),
				'encoder_hidden_states': encoderHiddenStates,
				"use_cache_branch": np.array([1], dtype=np.bool_),
			}

			# Add past_key_values to inputs
			decoderInputs.update(pastKeyValues)

			# Run decoder
			decoderOutputs = self.decoderSession.run(None, decoderInputs)
			logits = decoderOutputs[0]  # Shape: (batch_size, seq_len, vocab_size)

			# Greedy selection of next token
			nextTokenLogits = logits[0, -1, :]  # Logits for last position
			nextTokenId = int(np.argmax(nextTokenLogits))

			# Check if generation should end
			if nextTokenId == self.eosTokenId:
				break

			generatedTokens.append(nextTokenId)

			# Update past_key_values from outputs
			if len(decoderOutputs) > 1:
				for layerIdx in range(self.nLayer):
					if len(decoderOutputs) > 1 + layerIdx * 2 + 1:
						pastKeyValues[f'past_key_values.{layerIdx}.key'] = decoderOutputs[1 + layerIdx * 2]
						pastKeyValues[f'past_key_values.{layerIdx}.value'] = decoderOutputs[1 + layerIdx * 2 + 1]

			# Avoid sequences that are too long
			if len(generatedTokens) >= self.nCtx - 1:
				break

		# Decode generated text
		return self.decodeTokens(generatedTokens)

	def _softmax(self, x: np.ndarray) -> np.ndarray:
		"""Compute softmax activation.
		
		Args:
			x: Input array.
			
		Returns:
			Softmax-activated array.
		"""
		expX = np.exp(x - np.max(x))
		return expX / np.sum(expX)

	def generate_caption(self, image: str| bytes, 
						 maxLength: int| None = None) -> str:
		"""Generate image caption.

		Args:
			image: Image file path or binary data.
			maxLength: Maximum generation length.

		Returns:
			Generated image caption.
		"""
		# Preprocess image
		imageArray = self.preprocessImage(image)

		# Encode image
		encoderHiddenStates = self.encodeImage(imageArray)

		# Generate text
		caption = self.generateWithGreedy(encoderHiddenStates, maxLength)

		return caption


def createConfigFile(configDict: dict, savePath: str = "config.json") -> None:
	"""Create configuration file.

	Args:
		configDict: Configuration dictionary.
		savePath: Path to save the configuration file.
	"""
	with open(savePath, 'w', encoding='utf-8') as f:
		json.dump(configDict, f, indent=2, ensure_ascii=False)
	print(f"Config saved to {savePath}")


def benchmarkInference(captioner: ImageCaptioner, 
					   imagePath: str, numRuns: int = 10) -> None:
	"""Benchmark inference performance.

	Args:
		captioner: Model instance.
		imagePath: Test image path.
		numRuns: Number of runs for benchmarking.
	"""
	print(f"Running benchmark with {numRuns} iterations...")

	# Warm up
	captioner.generate_caption(imagePath)

	# Test greedy search
	startTime = time.time()
	for _ in range(numRuns):
		captioner.generate_caption(imagePath)
	greedyTime = (time.time() - startTime) / numRuns

	print(f"Average inference time:")
	print(f"  Greedy search: {greedyTime:.3f}s")


def main() -> None:
	"""Main function example."""
	# Initialize model - config_path is now required
	captioner = ImageCaptioner(
		encoder_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/onnx/encoder_model_quantized.onnx",
		decoder_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/onnx/decoder_model_merged_quantized.onnx",
		config_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/config.json",
		enableProfiling=True
	)

	print("=== Single Image Caption ===")
	caption1 = captioner.generate_caption(image="porridge.png")
	print(f"result: {caption1}")
	benchmarkInference(captioner=captioner, imagePath="porridge.png")



if __name__ == "__main__":
	main()