# -*- coding: UTF-8 -*-
import os, sys
from  .captioner import  LightweightONNXCaptioner
from .modelManager import  ModelManagerFrame
from .panel import  CaptionLocalSettingsPanel
import base64
import gui
from gui import guiHelper
import config
import scriptHandler
import json
import ui
import globalPluginHandler
import io
import threading 
import api
import wx
import addonHandler 
addonHandler.initTranslation()
here = os.path.dirname(__file__) 
models_dir = os.path.join(here, "..", "..", "models")
models_dir = os.path.abspath(models_dir)
confspec = {
    "localModelPath": f"string(default={models_dir}/Xenova/vit-gpt2-image-captioning)",
    "loadModelWhenInit":"boolean(default=true)"

}
config.conf.spec['captionLocal']=confspec
def shootImage():
    # 获取当前屏幕上聚焦的对象，通常是一个导航对象
    obj = api.getNavigatorObject()
    # ui.message("shooting")
    
    # 获取对象的位置和尺寸信息，即 x 和 y 位置，以及宽度和高度
    x, y, width, height = obj.location
    
    # 创建一个与对象尺寸相同的空白位图，准备在其上绘制图像
    bmp = wx.Bitmap(width, height)
    
    # 创建一个内存设备上下文，用于在位图上进行绘图操作
    mem = wx.MemoryDC(bmp)
    # ui.message("create memory")
    
    # 将屏幕上的指定区域（由 x, y, width, height 指定）复制到内存位图中
    mem.Blit(0, 0, width, height, wx.ScreenDC(), x, y)
    
    # 将位图转换为图像对象，这样可以进行更灵活的图像操作
    image = bmp.ConvertToImage()
    
    # 创建一个字节流对象，用于将图像数据保存为二进制数据（例如 PNG 格式）
    body = io.BytesIO()
    
    # 将图像保存到字节流中，使用 PNG 格式
    image.SaveFile(body, wx.BITMAP_TYPE_JPEG)
    
    # 从字节流对象中读取图像的二进制数据，以便进一步处理或保存
    image_data = body.getvalue()
    return  image_data

def caption(captioner: LightweightONNXCaptioner, image_data):
    try:
        description = captioner.generate_caption(image=image_data)
        ui.message(description)
        api.copyToClip(text=description, notify=False)
    except Exception as e:
        ui.message(str(e))

class GlobalPlugin(globalPluginHandler.GlobalPlugin):


    def __init__(self):
        super().__init__()
        self.is_model_loaded = False
        loadModelWhenInit = config.conf['captionLocal']['loadModelWhenInit']
        # load model when init plugin, may cause high memory useage 
        if loadModelWhenInit:
            threading.Thread(target=self._loadModel, daemon=True).start()
        gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(CaptionLocalSettingsPanel)

    
    def terminate(self):
        try:
            NVDASettingsDialog.categoryClasses.remove(CaptionLocalSettingsPanel)
        except:
            pass


    @scriptHandler.script(
        description=_("image caption  using local model"),
        # Translators: Category of addon in input gestures.
        # category= _("Local Image Caption"),
        category= _("Caption Local"),
        gesture="kb:NVDA+windows+,"
    )
    def script_runCaption(self, gesture):
        image_data= shootImage()
        # ui.message("got image")

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
            localModelDirPath = config.conf['captionLocal']['localModelPath']
            encoder_path=f"{localModelDirPath}/onnx/encoder_model_quantized.onnx"
            decoder_path = f"{localModelDirPath}/onnx/decoder_model_merged_quantized.onnx"
            config_path = f"{localModelDirPath}/config.json"  
            self.captioner = LightweightONNXCaptioner(
                encoder_path=encoder_path,
                decoder_path=decoder_path,
                config_path=config_path,
            )
            self.is_model_loaded = True
        except Exception as e:
            self.is_model_loaded =False
            ui.message(str(e))
            raise
    
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
            ui.message("model released and memory freed")
            self.is_model_loaded = False
        except Exception as e:
            ui.message(str(e))
            raise

    @scriptHandler.script(
        description=_("open  model manager"),
        # Translators: Category of addon in input gestures.
        category= _("Caption Local"),
        gesture="kb:NVDA+windows+control+,"
    )
    def script_openManager(self, gesture): 
        ui.message("openning model manager...")
        try:
            self._openModelManager()

        except Exception as e:
            ui.message(str(e))
            raise



    def _openModelManager(self):
        def show_manager():
            try:
                # 使用现有的wx.App（如果有的话）
                app = wx.GetApp()
                if app is None:
                    app = wx.App()
                
                if not hasattr(self, 'manager_frame') or not self.manager_frame:
                    self.manager_frame = ModelManagerFrame()
                
                self.manager_frame.Show()
                self.manager_frame.Raise()
                
            except Exception as e:
                ui.message(str(e))
        
        # 确保在主线程执行
        wx.CallAfter(show_manager)

        # __gestures={
        # "kb:nvda+windows+,":"runCaption",
    # }

