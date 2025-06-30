import os
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple
import threading
import time

def ensure_models_directory(base_path: Optional[str] = None) -> str:
    """
    确保models目录存在，如果不存在则创建
    
    Args:
        base_path: 基础路径，默认使用__file__的父目录
        
    Returns:
        str: models目录的绝对路径
        
    Raises:
        OSError: 创建目录失败时抛出异常
    """
    if base_path is None:
        here = os.path.dirname(__file__)
    else:
        here = base_path
        
    models_dir = os.path.join(here, "..", "..", "models")
    models_dir = os.path.abspath(models_dir)
    
    try:
        Path(models_dir).mkdir(parents=True, exist_ok=True)
        print(f"Models directory ensured: {models_dir}")
        return models_dir
    except OSError as e:
        raise OSError(f"Failed to create models directory {models_dir}: {e}")

def construct_download_url(remote_host: str, model_name: str, file_path: str, 
                          resolve_path: str = "/resolve/main") -> str:
    """
    构造下载URL
    
    Args:
        remote_host: 远程主机地址
        model_name: 模型名称
        file_path: 文件路径
        resolve_path: 解析路径，默认为/resolve/main
        
    Returns:
        str: 完整的下载URL
    """
    # 确保所有路径组件都正确格式化
    if not remote_host.startswith(('http://', 'https://')):
        remote_host = f"https://{remote_host}"
    
    # 移除多余的斜杠并构造URL
    base_url = remote_host.rstrip('/')
    model_name = model_name.strip('/')
    resolve_path = resolve_path.strip('/')
    file_path = file_path.lstrip('/')
    
    url = f"{base_url}/{model_name}/{resolve_path}/{file_path}"
    return url

def download_single_file(url: str, local_path: str, max_retries: int = 3) -> Tuple[bool, str]:
    """
    下载单个文件
    
    Args:
        url: 下载URL
        local_path: 本地保存路径
        max_retries: 最大重试次数
        
    Returns:
        Tuple[bool, str]: (是否成功, 错误信息或成功信息)
    """
    thread_id = threading.current_thread().ident
    
    # 确保本地目录存在
    local_dir = os.path.dirname(local_path)
    try:
        Path(local_dir).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"Failed to create directory {local_dir}: {e}"
    
    # 如果文件已存在，检查是否需要重新下载
    if os.path.exists(local_path):
        print(f"[Thread-{thread_id}] File already exists: {local_path}")
        return True, f"File already exists: {local_path}"
    
    for attempt in range(max_retries):
        try:
            print(f"[Thread-{thread_id}] Downloading (attempt {attempt + 1}/{max_retries}): {url}")
            
            # 创建请求对象并设置User-Agent
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Python urllib)')
            
            # 下载文件
            with urllib.request.urlopen(req, timeout=30) as response:
                # 获取文件大小
                content_length = response.headers.get('Content-Length')
                if content_length:
                    total_size = int(content_length)
                    print(f"[Thread-{thread_id}] File size: {total_size:,} bytes")
                
                # 写入文件
                with open(local_path, 'wb') as f:
                    downloaded = 0
                    chunk_size = 8192
                    
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 显示进度（每MB显示一次）
                        if downloaded % (1024 * 1024) == 0 or downloaded == total_size:
                            if content_length:
                                progress = (downloaded / total_size) * 100
                                print(f"[Thread-{thread_id}] Progress: {progress:.1f}% ({downloaded:,}/{total_size:,} bytes)")
            
            # 验证下载的文件
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                success_msg = f"Successfully downloaded: {local_path}"
                print(f"[Thread-{thread_id}] {success_msg}")
                return True, success_msg
            else:
                raise Exception("Downloaded file is empty or doesn't exist")
                
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP Error {e.code}: {e.reason} for URL: {url}"
            print(f"[Thread-{thread_id}] {error_msg}")
            if e.code == 404:
                return False, f"File not found (404): {url}"
            if attempt == max_retries - 1:
                return False, error_msg
        except urllib.error.URLError as e:
            error_msg = f"URL Error: {e.reason} for URL: {url}"
            print(f"[Thread-{thread_id}] {error_msg}")
            if attempt == max_retries - 1:
                return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e} for URL: {url}"
            print(f"[Thread-{thread_id}] {error_msg}")
            if attempt == max_retries - 1:
                return False, error_msg
        
        # 重试前等待
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt  # 指数退避
            print(f"[Thread-{thread_id}] Waiting {wait_time} seconds before retry...")
            time.sleep(wait_time)
    
    return False, f"Failed to download after {max_retries} attempts: {url}"

def download_models_multithreaded(
    remote_host: str = "huggingface.co",
    model_name: str = "Xenova/vit-gpt2-image-captioning", 
    files_to_download: Optional[List[str]] = None,
    resolve_path: str = "/resolve/main",
    max_workers: int = 4,
    base_path: Optional[str] = None
) -> Tuple[List[str], List[str]]:
    """
    多线程下载模型文件
    
    Args:
        remote_host: 远程主机，默认huggingface.co
        model_name: 模型名称，默认Xenova/vit-gpt2-image-captioning
        files_to_download: 要下载的文件列表，如果为None则使用默认列表
        resolve_path: 解析路径，默认/resolve/main
        max_workers: 最大线程数，默认4
        base_path: 基础路径，默认使用__file__的父目录
        
    Returns:
        Tuple[List[str], List[str]]: (成功下载的文件列表, 失败的文件列表)
        
    Raises:
        ValueError: 参数无效时抛出
        OSError: 目录操作失败时抛出
    """
    # 验证参数
    if not remote_host or not model_name:
        raise ValueError("remote_host and model_name cannot be empty")
    
    # 默认文件列表
    if files_to_download is None:
        files_to_download = [
            "onnx/encoder_model_quantized.onnx",
            "onnx/decoder_model_merged_quantized.onnx", 
            "config.json",
            "vocab.json"
        ]
    
    if not files_to_download:
        raise ValueError("files_to_download cannot be empty")
    
    print(f"Starting download of {len(files_to_download)} files for model: {model_name}")
    print(f"Remote host: {remote_host}")
    print(f"Max workers: {max_workers}")
    
    # 确保models目录存在
    models_dir = ensure_models_directory(base_path)
    
    # 创建本地模型目录
    local_model_dir = os.path.join(models_dir, model_name)
    
    # 准备下载任务
    download_tasks = []
    for file_path in files_to_download:
        url = construct_download_url(remote_host, model_name, file_path, resolve_path)
        local_path = os.path.join(local_model_dir, file_path)
        download_tasks.append((url, local_path, file_path))
    
    successful_downloads = []
    failed_downloads = []
    
    # 使用线程池执行下载
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有下载任务
        future_to_task = {
            executor.submit(download_single_file, url, local_path): (url, local_path, file_path)
            for url, local_path, file_path in download_tasks
        }
        
        # 处理完成的任务
        for future in as_completed(future_to_task):
            url, local_path, file_path = future_to_task[future]
            try:
                success, message = future.result()
                if success:
                    successful_downloads.append(file_path)
                    print(f"✓ Success: {file_path}")
                else:
                    failed_downloads.append(file_path)
                    print(f"✗ Failed: {file_path} - {message}")
            except Exception as e:
                failed_downloads.append(file_path)
                print(f"✗ Exception for {file_path}: {e}")
    
    # 打印下载摘要
    print(f"\n=== Download Summary ===")
    print(f"Total files: {len(files_to_download)}")
    print(f"Successful: {len(successful_downloads)}")
    print(f"Failed: {len(failed_downloads)}")
    
    if successful_downloads:
        print(f"\nSuccessful downloads:")
        for file_path in successful_downloads:
            print(f"  ✓ {file_path}")
    
    if failed_downloads:
        print(f"\nFailed downloads:")
        for file_path in failed_downloads:
            print(f"  ✗ {file_path}")
    
    print(f"\nLocal model directory: {local_model_dir}")
    
    return successful_downloads, failed_downloads

def get_model_file_paths(model_name: str = "Xenova/vit-gpt2-image-captioning", 
                        base_path: Optional[str] = None) -> dict:
    """
    获取模型文件的本地路径
    
    Args:
        model_name: 模型名称
        base_path: 基础路径，默认使用__file__的父目录
        
    Returns:
        dict: 包含各个文件路径的字典
    """
    models_dir = ensure_models_directory(base_path)
    local_model_dir = os.path.join(models_dir, model_name)
    
    return {
        'encoder_path': os.path.join(local_model_dir, "onnx", "encoder_model_quantized.onnx"),
        'decoder_path': os.path.join(local_model_dir, "onnx", "decoder_model_merged_quantized.onnx"),
        'config_path': os.path.join(local_model_dir, "config.json"),
        'vocab_path': os.path.join(local_model_dir, "vocab.json"),
        'model_dir': local_model_dir
    }

# 使用示例
if __name__ == "__main__":
    try:
        # 下载默认模型
        successful, failed = download_models_multithreaded()
        
        if not failed:
            print("\n🎉 All files downloaded successfully!")
            
            # 获取文件路径
            paths = get_model_file_paths()
            print(f"\nModel file paths:")
            for key, path in paths.items():
                print(f"  {key}: {path}")
        else:
            print(f"\n⚠️  Some files failed to download: {failed}")
            
    except Exception as e:
        print(f"Error: {e}")
        