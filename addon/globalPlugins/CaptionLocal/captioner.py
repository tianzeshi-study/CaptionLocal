import onnxruntime as ort
import numpy as np
from PIL import Image
import json
import re
import os
from typing import List, Dict, Union, Optional
import io

class LightweightONNXCaptioner:
    """
    轻量级 ONNX Runtime 图像描述模型
    不依赖 PyTorch，只使用 ONNX Runtime + 基础库
    """

    def __init__(self, encoder_path: str, decoder_path: str, config_path: str):
        """
        初始化轻量级 ONNX 图像描述模型

        Args:
            encoder_path: ViT 编码器 ONNX 模型路径
            decoder_path: GPT-2 解码器 ONNX 模型路径
            config_path: 配置文件路径（必选）
        """
        # 加载配置文件
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"config file  {config_path} not fount, please download models and  config first!")
        except Exception as e:
            print(e)
            raise


        # 自动加载词汇表（vocab.json在config.json同目录下）
        config_dir = os.path.dirname(config_path)
        vocab_path = os.path.join(config_dir, 'vocab.json')
        self.vocab = self._load_vocab(vocab_path)
        self.vocab_size = len(self.vocab)

        # 从配置文件加载所有模型参数
        self._load_model_params()



        # 加载 ONNX 模型
        self.encoder_session = ort.InferenceSession(encoder_path)
        self.decoder_session = ort.InferenceSession(decoder_path)

        print(f"Loaded ONNX models - Encoder: {encoder_path}, Decoder: {decoder_path}")
        print(f"Loaded config from: {config_path}")
        print(f"Loaded vocabulary from: {vocab_path}")
        print(f"Model config - Image size: {self.image_size}, Max length: {self.max_length}")

    def _load_model_params(self):
        """从配置文件加载所有模型参数"""
        # 编码器参数
        encoder_config = self.config.get('encoder', {})
        self.image_size = encoder_config.get('image_size', 224)
        self.num_channels = encoder_config.get('num_channels', 3)
        self.patch_size = encoder_config.get('patch_size', 16)
        self.encoder_hidden_size = encoder_config.get('hidden_size', 768)
        self.encoder_num_layers = encoder_config.get('num_hidden_layers', 12)
        self.encoder_num_heads = encoder_config.get('num_attention_heads', 12)
        self.encoder_intermediate_size = encoder_config.get('intermediate_size', 3072)

        # 解码器参数
        decoder_config = self.config.get('decoder', {})
        self.max_length = decoder_config.get('max_length', 20)
        self.decoder_vocab_size = decoder_config.get('vocab_size', 50257)
        self.n_embd = decoder_config.get('n_embd', 768)
        self.n_layer = decoder_config.get('n_layer', 12)
        self.n_head = decoder_config.get('n_head', 12)
        self.n_ctx = decoder_config.get('n_ctx', 1024)
        self.n_positions = decoder_config.get('n_positions', 1024)

        # 特殊token ID
        self.bos_token_id = self.config.get('bos_token_id', 50256)
        self.eos_token_id = self.config.get('eos_token_id', 50256)
        self.pad_token_id = self.config.get('pad_token_id', 50256)

        # 生成参数
        generation_config = self.config.get('generation', {})
        self.do_sample = generation_config.get('do_sample', False)
        self.num_beams = generation_config.get('num_beams', 1)
        self.temperature = generation_config.get('temperature', 1.0)
        self.top_k = generation_config.get('top_k', 50)
        self.top_p = generation_config.get('top_p', 1.0)
        self.repetition_penalty = generation_config.get('repetition_penalty', 1.0)
        self.length_penalty = generation_config.get('length_penalty', 1.0)

    def _load_vocab(self, vocab_path: str) -> Dict[int, str]:
        """
        加载词汇表文件

        Args:
            vocab_path: vocab.json 文件路径

        Returns:
            vocab: 词汇表字典 (id -> token)
        """
        try:
            with open(vocab_path, 'r', encoding='utf-8') as f:
                vocab_data = json.load(f)

            # 转换为 id -> token 格式
            vocab = {v: k for k, v in vocab_data.items()}
            print(f"Successfully loaded vocabulary with {len(vocab)} tokens")
            return vocab

        except FileNotFoundError:
            print(f"Warning: vocab.json not found at {vocab_path}")
            print("Using fallback vocabulary")
            return self._get_fallback_vocab()
        except Exception as e:
            print(f"Warning: Could not load vocabulary from {vocab_path}: {e}")
            print("Using fallback vocabulary")
            return self._get_fallback_vocab()

    def _get_fallback_vocab(self) -> Dict[int, str]:
        """
        构建简化的备用词汇表
        """
        # 基础特殊 token
        vocab = {
            50256: '<|endoftext|>',  # BOS/EOS/PAD token
            50257: '<|pad|>',
        }

        # 常见单词（这里只是示例，实际需要完整词汇表）
        common_words = [
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

        # 添加常见单词到词汇表
        for i, word in enumerate(common_words):
            if i < 50256:  # 避免与特殊token冲突
                vocab[i] = word

        print(f"Built fallback vocabulary with {len(vocab)} tokens")
        return vocab

    def preprocess_image(self, image: Union[str, bytes]) -> np.ndarray:
        """
        预处理图像

        Args:
            image: 图像路径或 PIL Image 对象

        Returns:
            preprocessed_image: 预处理后的图像数组
        """
        if isinstance(image, str):
            img = Image.open(image).convert('RGB')
        else:
            img = Image.open(io.BytesIO(image)).convert('RGB')

        # 调整图像大小
        img = img.resize((self.image_size, self.image_size), Image.LANCZOS)

        # 转换为 numpy 数组并归一化到 [0, 1]
        img_array = np.array(img).astype(np.float32) / 255.0

        # ImageNet 标准化
        mean = np.array([0.485, 0.456, 0.406])
        std = np.array([0.229, 0.224, 0.225])
        img_array = (img_array - mean) / std

        # 调整维度: (H, W, C) -> (1, C, H, W)
        img_array = np.transpose(img_array, (2, 0, 1))
        img_array = np.expand_dims(img_array, axis=0)

        return img_array

    def encode_image(self, image_array: np.ndarray) -> np.ndarray:
        """
        使用 ViT 编码器编码图像

        Args:
            image_array: 预处理后的图像数组

        Returns:
            encoder_hidden_states: 编码器输出特征
        """
        # 获取编码器输入输出名称
        input_name = self.encoder_session.get_inputs()[0].name

        # 运行编码器推理
        image_array = image_array.astype(np.float32)
        encoder_outputs = self.encoder_session.run(None, {input_name: image_array})

        # 返回最后一层隐藏状态
        return encoder_outputs[0]

    def decode_tokens(self, token_ids: List[int]) -> str:
        """
        将 token ID 解码为文本

        Args:
            token_ids: token ID 列表

        Returns:
            decoded_text: 解码后的文本
        """
        tokens = []
        for token_id in token_ids:
            if token_id in self.vocab:
                token = self.vocab[token_id]

                if token not in ['<|endoftext|>', '<|pad|>']:
                    tokens.append(token)

        # 简单的文本后处理
        text = ' '.join(tokens).replace("Ġ", " ")

        # 基础的文本清理
        text = re.sub(r'\s+', ' ', text)  # 多个空格合并为一个
        text = text.strip()

        return text

    def get_decoder_input_names(self) -> List[str]:
        """获取解码器的输入名称，用于调试"""
        return [inp.name for inp in self.decoder_session.get_inputs()]

    def get_decoder_output_names(self) -> List[str]:
        """获取解码器的输出名称，用于调试"""
        return [out.name for out in self.decoder_session.get_outputs()]

    def print_model_info(self):
        """打印模型信息，用于调试"""
        print("=== Encoder Model Info ===")
        for i, inp in enumerate(self.encoder_session.get_inputs()):
            print(f"Input {i}: {inp.name}, shape: {inp.shape}, type: {inp.type}")
        for i, out in enumerate(self.encoder_session.get_outputs()):
            print(f"Output {i}: {out.name}, shape: {out.shape}, type: {out.type}")

        print("\n=== Decoder Model Info ===")
        for i, inp in enumerate(self.decoder_session.get_inputs()):
            print(f"Input {i}: {inp.name}, shape: {inp.shape}, type: {inp.type}")
        for i, out in enumerate(self.decoder_session.get_outputs()):
            print(f"Output {i}: {out.name}, shape: {out.shape}, type: {out.type}")

    def _initialize_past_key_values(self, batch_size: int = 1) -> Dict[str, np.ndarray]:
        """
        初始化past_key_values

        Args:
            batch_size: 批次大小

        Returns:
            past_key_values: 初始化的past_key_values字典
        """
        past_key_values = {}

        # 为每一层创建key和value
        for layer_idx in range(self.n_layer):
            # key和value的形状: (batch_size, num_heads, 0, head_dim)
            # 初始时序列长度为0
            head_dim = self.n_embd // self.n_head

            key_shape = (batch_size, self.n_head, 0, head_dim)
            value_shape = (batch_size, self.n_head, 0, head_dim)

            past_key_values[f'past_key_values.{layer_idx}.key'] = np.zeros(key_shape, dtype=np.float32)
            past_key_values[f'past_key_values.{layer_idx}.value'] = np.zeros(value_shape, dtype=np.float32)

        return past_key_values

    def generate_with_greedy(self, encoder_hidden_states: np.ndarray, max_length: Optional[int] = None) -> str:
        """
        使用贪婪搜索生成文本

        Args:
            encoder_hidden_states: 编码器隐藏状态
            max_length: 最大生成长度

        Returns:
            generated_text: 生成的文本
        """
        if max_length is None:
            max_length = self.max_length

        # 初始化输入序列
        input_ids = np.array([[self.bos_token_id]], dtype=np.int64)
        generated_tokens = []

        # 初始化past_key_values
        past_key_values = self._initialize_past_key_values(batch_size=1)

        for step in range(max_length):
            # 准备解码器输入
            decoder_inputs = {
                'input_ids': input_ids if step == 0 else np.array([[generated_tokens[-1]]], dtype=np.int64),
                'encoder_hidden_states': encoder_hidden_states,
                # "use_cache_branch": np.array([1], dtype=np.int64),  # 使用缓存
                "use_cache_branch": np.array([1], dtype=np.bool),
            }

            # 添加past_key_values到输入
            decoder_inputs.update(past_key_values)

            # 运行解码器
            # for inp in self.decoder_session.get_inputs():
                # print(f"name = {inp.name}, type = {inp.type}")
            decoder_outputs = self.decoder_session.run(None, decoder_inputs)
            logits = decoder_outputs[0]  # 形状: (batch_size, seq_len, vocab_size)


            # 贪婪选择下一个 token
            next_token_logits = logits[0, -1, :]  # 最后一个位置的 logits
            next_token_id = int(np.argmax(next_token_logits))

            # 检查是否结束
            if next_token_id == self.eos_token_id:
                break

            generated_tokens.append(next_token_id)


            # 更新past_key_values（从输出中获取）
            if len(decoder_outputs) > 1:
                # 更新past_key_values
                for layer_idx in range(self.n_layer):
                    if len(decoder_outputs) > 1 + layer_idx * 2 + 1:
                        past_key_values[f'past_key_values.{layer_idx}.key'] = decoder_outputs[1 + layer_idx * 2]
                        past_key_values[f'past_key_values.{layer_idx}.value'] = decoder_outputs[1 + layer_idx * 2 + 1]

            # 避免序列过长
            if len(generated_tokens) >= self.n_ctx - 1:
                break

        # 解码生成的文本
        return self.decode_tokens(generated_tokens)

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """计算 softmax"""
        exp_x = np.exp(x - np.max(x))
        return exp_x / np.sum(exp_x)

    def generate_caption(self, image: Union[str, bytes],
                        max_length: Optional[int] = None,
                        ) -> str:
        """
        生成图像描述

        Args:
            image: 图像路径或二进制数据

            max_length: 最大生成长度


        Returns:
            caption: 生成的图像描述
        """
        # 预处理图像
        image_array = self.preprocess_image(image)

        # 编码图像
        encoder_hidden_states = self.encode_image(image_array)

        # 生成文本
        caption = self.generate_with_greedy(encoder_hidden_states, max_length)

        return caption

# 使用示例
def main():
    """主函数示例"""

    # 初始化模型 - config_path现在是必选参数
    captioner = LightweightONNXCaptioner(
        encoder_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/onnx/encoder_model_quantized.onnx",
        decoder_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/onnx/decoder_model_merged_quantized.onnx",
        config_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/config.json"  # 必选
    )



    print("=== 单张图片描述 ===")
    caption1 = captioner.generate_caption(image="porridge.png")
    print(f"Greedy: {caption1}")
    benchmark_inference(captioner, "porridge.png", 5)


# 配置文件创建工具
def create_config_file(config_dict: dict, save_path: str = "config.json"):
    """
    创建配置文件

    Args:
        config_dict: 配置字典
        save_path: 保存路径
    """
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=2, ensure_ascii=False)
    print(f"Config saved to {save_path}")

# 性能测试
def benchmark_inference(captioner, image_path: str, num_runs: int = 10):
    """
    性能测试

    Args:
        captioner: 模型实例
        image_path: 测试图像路径
        num_runs: 运行次数
    """
    import time

    print(f"Running benchmark with {num_runs} iterations...")

    # 预热
    captioner.generate_caption(image_path)

    # 测试贪婪搜索
    start_time = time.time()
    for _ in range(num_runs):
        captioner.generate_caption(image_path)
    greedy_time = (time.time() - start_time) / num_runs



    print(f"Average inference time:")
    print(f"  Greedy search: {greedy_time:.3f}s")


if __name__ == "__main__":
    main()