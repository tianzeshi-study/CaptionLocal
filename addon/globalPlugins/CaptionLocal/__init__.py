import os, sys
here = os.path.dirname(__file__) 
sys.path.insert(0, here)
from  captioner import  LightweightONNXCaptioner
import base64
import gui, wx
from gui import guiHelper
import textInfos
import scriptHandler
import json
import ui
import globalPluginHandler
import tones # We want to hear beeps.
import subprocess
import io
import threading 
import api
import wx
import urllib.request
import urllib.error

#Insure one instance of Search with dialog is active.
_searchWithDialog= None


# 构建请求的 URL（服务器的接收端点）,第一个打算弃用,它不支持提问,而且没有多语言支持, 只能输出中文, 而且有时会冒两句英文
# url = 'https://caption.flowersky.love'  
url = 'https://caption.aiursoft.tech'  
# queryUrl = "http://localhost:8787"
# queryUrl = "https://vision.flowersky.love"
queryUrl = "https://vision.aiursoft.tech"

# 构建请求头，包括内容类型和 Bearer API Key
headers = {
    "User-Agent": "curl/7.68.0",  # 这里模拟的是curl的请求头
    # 'Content-Type': 'image/png',  # 指定内容类型为 PNG 图像
    'Content-Type': 'application/json', 
    'Authorization': 'Bearer luckydog'  # 使用 Bearer 认证，将 'YOUR_API_KEY' 替换为实际的 API Key
}


def isSelectedText():
    '''this function  specifies if a certain text is selected or not
        and if it is, returns text selected.
    '''
    obj=api.getFocusObject()
    treeInterceptor=obj.treeInterceptor
    if hasattr(treeInterceptor,'TextInfo') and not treeInterceptor.passThrough:
        obj=treeInterceptor
    try:
        info=obj.makeTextInfo(textInfos.POSITION_SELECTION)
    except (RuntimeError, NotImplementedError, LookupError):
        info=None
    if not info or info.isCollapsed:
        return False
    else:
        return info.text.strip()

def shootImage():
    # 获取当前屏幕上聚焦的对象，通常是一个导航对象（可能表示当前窗口或屏幕的某一部分）
    obj = api.getNavigatorObject()
    
    # 获取对象的位置和尺寸信息，即 x 和 y 位置，以及宽度和高度
    x, y, width, height = obj.location
    
    # 如果启用了 sizeReport 选项，并且脚本没有被重复调用（通常与按键脚本相关）
    # 这里的代码被注释掉了，通常用于报告尺寸
    # if conf["sizeReport"] and scriptHandler.getLastScriptRepeatCount() != 1:
    #    ui.message(_("Size: {width} X {height} pixels").format(width=width, height=height))
    
    # 创建一个与对象尺寸相同的空白位图，准备在其上绘制图像
    bmp = wx.Bitmap(width, height)
    
    # 创建一个内存设备上下文，用于在位图上进行绘图操作
    mem = wx.MemoryDC(bmp)
    
    # 将屏幕上的指定区域（由 x, y, width, height 指定）复制到内存位图中
    mem.Blit(0, 0, width, height, wx.ScreenDC(), x, y)
    
    # 将位图转换为图像对象，这样可以进行更灵活的图像操作
    image = bmp.ConvertToImage()
    
    # 创建一个字节流对象，用于将图像数据保存为二进制数据（例如 PNG 格式）
    body = io.BytesIO()
    
    # 将图像保存到字节流中，使用 PNG 格式
    image.SaveFile(body, wx.BITMAP_TYPE_PNG)
    
    # 从字节流对象中读取图像的二进制数据，以便进一步处理或保存
    image_data = body.getvalue()
    return  image_data

def caption(captioner: LightweightONNXCaptioner, image_data):
    # image_data 是要发送的图像的二进制数据（假设之前已经从 BytesIO 对象中读取）



    # captioner = LightweightONNXCaptioner(
        # encoder_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/onnx/encoder_model_quantized.onnx",
        # decoder_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/onnx/decoder_model_merged_quantized.onnx",
        # config_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/config.json"  # 必选
    # )


    try:
        # description = captioner.generate_caption(image="D:/mypython/nvda/addons/plugin/captionLocal/addon/globalPlugins/CaptionLocal/porridge.png")
        description = captioner.generate_caption(image=image_data)
        ui.message(description)
        api.copyToClip(text=description, notify=False)
    except Exception as e:
        ui.message(str(e))

class GlobalPlugin(globalPluginHandler.GlobalPlugin):


    def __init__(self):
        super().__init__()
        self.is_model_loaded = False


    @scriptHandler.script(
        description=_("image caption  using local model"),
        # Translators: Category of addon in input gestures.
        # category= _("Local Image Caption"),
        category= _("Caption Local"),
        gesture="kb:NVDA+windows+,"
    )
    def script_runCaption(self, gesture):
        image_data= shootImage()
        ui.message("got image")

        if self.is_model_loaded: 
            pass
        else:
            ui.message("loading model...")
            self._loadModel()


        image_threading =threading.Thread(target=caption, args=(self.captioner, image_data,))
        ui.message("starting recognize")
        image_threading.start()

    def _loadModel(self): 
        try:
            self.captioner = LightweightONNXCaptioner(
                encoder_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/onnx/encoder_model_quantized.onnx",
                decoder_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/onnx/decoder_model_merged_quantized.onnx",
                config_path="D:/mypython/aitest/vlm/Xenova/vit-gpt2-image-captioning/config.json"  # 必选
            )
            self.is_model_loaded = True
        except Exception as e:
            self.is_model_loaded =False
            ui.message(e)
    
    @scriptHandler.script(
        description=_("release  local model"),
        # Translators: Category of addon in input gestures.
        # category= _("Local Image Caption"),
        category= _("Caption Local"),
        gesture="kb:NVDA+windows+shift+,"
    )
    def script_releaseModel(self, gesture): 
        ui.message("releasing model...")
        try:
            size = sys.getsizeof(self.captioner)
            del self.captioner 
            ui.message(f"freed {size} bytes of memory")
            self.is_model_loaded = False
        except Exception as e:
            ui.message(e)

        # __gestures={
        # "kb:nvda+windows+,":"runCaption",
    # }
