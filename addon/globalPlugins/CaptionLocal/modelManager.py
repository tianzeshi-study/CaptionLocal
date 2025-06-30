import wx
import os
import threading
from typing import List, Tuple, Optional
import sys

# 假设modelDownloader.py在同一目录下
try:
    from modelDownloader import download_models_multithreaded, ensure_models_directory, get_model_file_paths
except ImportError as e:
    print(f"Error importing modelDownloader: {e}")
    print("Please ensure modelDownloader.py is in the same directory")
    sys.exit(1)

class AdvancedSettingsDialog(wx.Dialog):
    """高级设置对话框"""
    
    def __init__(self, parent, model_name="Xenova/vit-gpt2-image-captioning", 
                 files_list=None, resolve_path="/resolve/main", use_mirror=False):
        super().__init__(parent, title="高级设置", size=(500, 400),
                        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        self.model_name = model_name
        self.files_list = files_list or [
            "onnx/encoder_model_quantized.onnx",
            "onnx/decoder_model_merged_quantized.onnx", 
            "config.json",
            "vocab.json"
        ]
        self.resolve_path = resolve_path
        self.use_mirror = use_mirror
        
        self._init_ui()
        self._bind_events()
        
    def _init_ui(self):
        """初始化界面"""
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建笔记本控件用于分组
        notebook = wx.Notebook(self)
        
        # 模型配置页面
        model_panel = wx.Panel(notebook)
        model_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 模型名称
        model_sizer.Add(wx.StaticText(model_panel, label="模型名称:"), 0, wx.ALL, 5)
        self.model_name_ctrl = wx.TextCtrl(model_panel, value=self.model_name, size=(400, -1))
        model_sizer.Add(self.model_name_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        
        # 解析路径
        model_sizer.Add(wx.StaticText(model_panel, label="解析路径:"), 0, wx.ALL, 5)
        self.resolve_path_ctrl = wx.TextCtrl(model_panel, value=self.resolve_path, size=(400, -1))
        model_sizer.Add(self.resolve_path_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        
        # 使用镜像
        self.use_mirror_cb = wx.CheckBox(model_panel, label="使用HuggingFace镜像 (hf-mirror.com)")
        self.use_mirror_cb.SetValue(self.use_mirror)
        model_sizer.Add(self.use_mirror_cb, 0, wx.ALL, 5)
        
        model_panel.SetSizer(model_sizer)
        notebook.AddPage(model_panel, "模型配置")
        
        # 文件列表页面
        files_panel = wx.Panel(notebook)
        files_sizer = wx.BoxSizer(wx.VERTICAL)
        
        files_sizer.Add(wx.StaticText(files_panel, label="要下载的文件列表:"), 0, wx.ALL, 5)
        
        # 文件列表控件
        self.files_listbox = wx.ListBox(files_panel, choices=self.files_list, 
                                       style=wx.LB_MULTIPLE | wx.LB_HSCROLL)
        # 默认选中所有文件
        for i in range(len(self.files_list)):
            self.files_listbox.SetSelection(i)
        files_sizer.Add(self.files_listbox, 1, wx.ALL | wx.EXPAND, 5)
        
        # 文件操作按钮
        file_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.add_file_btn = wx.Button(files_panel, label="添加文件")
        self.remove_file_btn = wx.Button(files_panel, label="移除文件")
        file_btn_sizer.Add(self.add_file_btn, 0, wx.ALL, 2)
        file_btn_sizer.Add(self.remove_file_btn, 0, wx.ALL, 2)
        files_sizer.Add(file_btn_sizer, 0, wx.ALL | wx.CENTER, 5)
        
        files_panel.SetSizer(files_sizer)
        notebook.AddPage(files_panel, "文件列表")
        
        main_sizer.Add(notebook, 1, wx.ALL | wx.EXPAND, 10)
        
        # 对话框按钮
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK, "确定")
        cancel_btn = wx.Button(self, wx.ID_CANCEL, "取消")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.CENTER, 10)
        
        self.SetSizer(main_sizer)
        
    def _bind_events(self):
        """绑定事件"""
        self.add_file_btn.Bind(wx.EVT_BUTTON, self.on_add_file)
        self.remove_file_btn.Bind(wx.EVT_BUTTON, self.on_remove_file)
        
    def on_add_file(self, event):
        """添加文件"""
        dlg = wx.TextEntryDialog(self, "请输入文件路径:", "添加文件")
        if dlg.ShowModal() == wx.ID_OK:
            file_path = dlg.GetValue().strip()
            if file_path and file_path not in self.files_list:
                self.files_list.append(file_path)
                self.files_listbox.Append(file_path)
                # 选中新添加的文件
                self.files_listbox.SetSelection(len(self.files_list) - 1)
        dlg.Destroy()
        
    def on_remove_file(self, event):
        """移除文件"""
        selection = self.files_listbox.GetSelection()
        if selection != wx.NOT_FOUND:
            self.files_list.pop(selection)
            self.files_listbox.Delete(selection)
            
    def get_settings(self) -> dict:
        """获取设置"""
        # 获取选中的文件
        selected_files = []
        for i in range(self.files_listbox.GetCount()):
            if self.files_listbox.IsSelected(i):
                selected_files.append(self.files_list[i])
        
        return {
            'model_name': self.model_name_ctrl.GetValue().strip(),
            'files_to_download': selected_files,
            'resolve_path': self.resolve_path_ctrl.GetValue().strip(),
            'use_mirror': self.use_mirror_cb.GetValue()
        }

class ProgressDialog(wx.Dialog):
    """下载进度对话框"""
    
    def __init__(self, parent, title="下载进度"):
        super().__init__(parent, title=title, size=(400, 200),
                        style=wx.DEFAULT_DIALOG_STYLE)
        
        self._init_ui()
        self.Centre()
        
    def _init_ui(self):
        """初始化界面"""
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 状态文本
        self.status_text = wx.StaticText(self, label="准备开始下载...")
        main_sizer.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 10)
        
        # 进度条
        self.progress_gauge = wx.Gauge(self, range=100, size=(350, 25))
        main_sizer.Add(self.progress_gauge, 0, wx.ALL | wx.EXPAND, 10)
        
        # 详细信息文本框
        self.detail_text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                      size=(350, 80))
        main_sizer.Add(self.detail_text, 1, wx.ALL | wx.EXPAND, 10)
        
        # 取消按钮
        self.cancel_btn = wx.Button(self, label="取消")
        main_sizer.Add(self.cancel_btn, 0, wx.ALL | wx.CENTER, 10)
        
        self.SetSizer(main_sizer)
        
    def update_progress(self, value: int, status: str = "", detail: str = ""):
        """更新进度"""
        wx.CallAfter(self._update_progress_safe, value, status, detail)
        
    def _update_progress_safe(self, value: int, status: str, detail: str):
        """线程安全的进度更新"""
        if not self.IsBeingDeleted():
            self.progress_gauge.SetValue(value)
            if status:
                self.status_text.SetLabel(status)
            if detail:
                self.detail_text.AppendText(f"{detail}\n")
                self.detail_text.SetInsertionPointEnd()

class ModelManagerFrame(wx.Frame):
    """模型管理器主框架"""
    
    def __init__(self):
        super().__init__(None, title="模型管理器", size=(600, 450))
        
        # 默认设置
        self.download_path = ""
        self.model_name = "Xenova/vit-gpt2-image-captioning"
        self.files_to_download = [
            "onnx/encoder_model_quantized.onnx",
            "onnx/decoder_model_merged_quantized.onnx", 
            "config.json",
            "vocab.json"
        ]
        self.resolve_path = "/resolve/main"
        self.use_mirror = False
        
        # 下载相关
        self.download_thread = None
        self.download_cancelled = False
        
        self._init_ui()
        self._init_default_path()
        self._bind_events()
        
        # 居中显示
        self.Centre()
        
    def _init_ui(self):
        """初始化用户界面"""
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 标题
        title_text = wx.StaticText(panel, label="模型下载管理器")
        title_font = title_text.GetFont()
        title_font.PointSize += 4
        title_font = title_font.Bold()
        title_text.SetFont(title_font)
        main_sizer.Add(title_text, 0, wx.ALL | wx.CENTER, 15)
        
        # 下载路径选择
        path_box = wx.StaticBoxSizer(wx.StaticBox(panel, label="下载设置"), wx.VERTICAL)
        
        path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        path_sizer.Add(wx.StaticText(panel, label="下载路径:"), 0, wx.ALL | wx.CENTER, 5)
        
        self.path_ctrl = wx.TextCtrl(panel, size=(350, -1))
        path_sizer.Add(self.path_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        
        self.browse_btn = wx.Button(panel, label="浏览...")
        path_sizer.Add(self.browse_btn, 0, wx.ALL, 5)
        
        path_box.Add(path_sizer, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(path_box, 0, wx.ALL | wx.EXPAND, 10)
        
        # 模型信息显示
        info_box = wx.StaticBoxSizer(wx.StaticBox(panel, label="模型信息"), wx.VERTICAL)
        
        self.model_info_text = wx.StaticText(panel, label=f"模型: {self.model_name}")
        info_box.Add(self.model_info_text, 0, wx.ALL, 5)
        
        self.files_info_text = wx.StaticText(panel, label=f"文件数量: {len(self.files_to_download)}")
        info_box.Add(self.files_info_text, 0, wx.ALL, 5)
        
        main_sizer.Add(info_box, 0, wx.ALL | wx.EXPAND, 10)
        
        # 操作按钮
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.advanced_btn = wx.Button(panel, label="高级设置...")
        btn_sizer.Add(self.advanced_btn, 0, wx.ALL, 5)
        
        btn_sizer.AddStretchSpacer(1)
        
        self.download_btn = wx.Button(panel, label="開始下载", size=(120, 35))
        self.download_btn.SetBackgroundColour(wx.Colour(0, 120, 215))
        self.download_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        btn_sizer.Add(self.download_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)
        
        # 状态栏
        self.status_text = wx.StaticText(panel, label="就绪")
        main_sizer.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 10)
        
        # 日志区域
        log_box = wx.StaticBoxSizer(wx.StaticBox(panel, label="下载日志"), wx.VERTICAL)
        self.log_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                   size=(550, 150))
        log_box.Add(self.log_text, 1, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(log_box, 1, wx.ALL | wx.EXPAND, 10)
        
        panel.SetSizer(main_sizer)
        
    def _init_default_path(self):
        """初始化默认路径"""
        try:
            default_path = ensure_models_directory()
            self.download_path = default_path
            self.path_ctrl.SetValue(default_path)
            self.log(f"默认下载路径: {default_path}")
        except Exception as e:
            self.log(f"初始化路径失败: {e}")
            
    def _bind_events(self):
        """绑定事件"""
        self.browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_path)
        self.advanced_btn.Bind(wx.EVT_BUTTON, self.on_advanced_settings)
        self.download_btn.Bind(wx.EVT_BUTTON, self.on_download)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
    def log(self, message: str):
        """添加日志信息"""
        wx.CallAfter(self._log_safe, message)
        
    def _log_safe(self, message: str):
        """线程安全的日志添加"""
        if not self.IsBeingDeleted():
            self.log_text.AppendText(f"{message}\n")
            self.log_text.SetInsertionPointEnd()
            
    def update_status(self, status: str):
        """更新状态"""
        wx.CallAfter(self._update_status_safe, status)
        
    def _update_status_safe(self, status: str):
        """线程安全的状态更新"""
        if not self.IsBeingDeleted():
            self.status_text.SetLabel(status)
            
    def on_browse_path(self, event):
        """浏览路径"""
        dlg = wx.DirDialog(self, "选择下载目录", defaultPath=self.download_path)
        if dlg.ShowModal() == wx.ID_OK:
            self.download_path = dlg.GetPath()
            self.path_ctrl.SetValue(self.download_path)
            self.log(f"下载路径更改为: {self.download_path}")
        dlg.Destroy()
        
    def on_advanced_settings(self, event):
        """高级设置"""
        dlg = AdvancedSettingsDialog(self, self.model_name, self.files_to_download,
                                   self.resolve_path, self.use_mirror)
        if dlg.ShowModal() == wx.ID_OK:
            settings = dlg.get_settings()
            self.model_name = settings['model_name']
            self.files_to_download = settings['files_to_download']
            self.resolve_path = settings['resolve_path']
            self.use_mirror = settings['use_mirror']
            
            # 更新显示信息
            self.model_info_text.SetLabel(f"模型: {self.model_name}")
            self.files_info_text.SetLabel(f"文件数量: {len(self.files_to_download)}")
            
            mirror_info = " (使用镜像)" if self.use_mirror else ""
            self.log(f"设置已更新: {self.model_name}{mirror_info}, {len(self.files_to_download)}个文件")
            
        dlg.Destroy()
        
    def on_download(self, event):
        """开始下载"""
        if self.download_thread and self.download_thread.is_alive():
            self.log("下载正在进行中...")
            return
            
        if not self.files_to_download:
            wx.MessageBox("请在高级设置中选择要下载的文件", "错误", wx.OK | wx.ICON_ERROR)
            return
            
        # 禁用下载按钮
        self.download_btn.Enable(False)
        self.download_cancelled = False
        
        # 启动下载线程
        self.download_thread = threading.Thread(target=self._download_worker)
        self.download_thread.daemon = True
        self.download_thread.start()
        
    def _download_worker(self):
        """下载工作线程"""
        try:
            self.update_status("下载中...")
            self.log("开始下载模型文件...")
            
            # 确定远程主机
            remote_host = "hf-mirror.com" if self.use_mirror else "huggingface.co"
            
            self.log(f"远程主机: {remote_host}")
            self.log(f"模型名称: {self.model_name}")
            self.log(f"下载路径: {self.download_path}")
            self.log(f"文件数量: {len(self.files_to_download)}")
            self.log("downloading... please wait")
            
            # 调用下载函数
            successful, failed = download_models_multithreaded(
                models_dir=self.download_path,
                remote_host=remote_host,
                model_name=self.model_name,
                files_to_download=self.files_to_download,
                resolve_path=self.resolve_path,
                max_workers=4,
                # base_path=os.path.dirname(self.download_path)
            )
            
            # 处理结果
            if not self.download_cancelled:
                self._handle_download_result(successful, failed)
                
        except Exception as e:
            self.log(f"下载过程中发生错误: {e}")
            self.update_status("下载失败")
            wx.CallAfter(self._show_error_message, f"下载失败: {e}")
        finally:
            wx.CallAfter(self._download_finished)
            
    def _handle_download_result(self, successful: List[str], failed: List[str]):
        """处理下载结果"""
        total = len(successful) + len(failed)
        
        if not failed:
            # 全部成功
            self.log(f"✅ 所有文件下载成功! ({len(successful)}/{total})")
            self.update_status("下载完成")
            wx.CallAfter(self._show_success_message, 
                        f"成功下载 {len(successful)} 个文件!\n\n模型已保存到:\n{self.download_path}")
        elif not successful:
            # 全部失败
            self.log(f"❌ 所有文件下载失败! ({len(failed)}/{total})")
            self.update_status("下载失败")
            wx.CallAfter(self._show_error_message, 
                        f"所有文件下载失败!\n\n失败的文件:\n" + "\n".join(failed))
        else:
            # 部分成功
            self.log(f"⚠️ 部分文件下载成功 ({len(successful)}/{total})")
            self.update_status("部分完成")
            wx.CallAfter(self._show_warning_message,
                        f"部分文件下载成功!\n\n成功: {len(successful)} 个\n失败: {len(failed)} 个\n\n失败的文件:\n" + "\n".join(failed))
            
    def _show_success_message(self, message: str):
        """显示成功消息"""
        wx.MessageBox(message, "下载成功", wx.OK | wx.ICON_INFORMATION)
        
    def _show_error_message(self, message: str):
        """显示错误消息"""
        wx.MessageBox(message, "下载失败", wx.OK | wx.ICON_ERROR)
        
    def _show_warning_message(self, message: str):
        """显示警告消息"""
        wx.MessageBox(message, "部分完成", wx.OK | wx.ICON_WARNING)
        
    def _download_finished(self):
        """下载完成后的清理工作"""
        self.download_btn.Enable(True)
        
    def on_close(self, event):
        """关闭事件"""
        if self.download_thread and self.download_thread.is_alive():
            self.download_cancelled = True
            dlg = wx.MessageDialog(self, "下载正在进行中，确定要退出吗?", "确认退出", 
                                 wx.YES_NO | wx.ICON_QUESTION)
            if dlg.ShowModal() != wx.ID_YES:
                dlg.Destroy()
                return
            dlg.Destroy()
        
        self.Destroy()

class ModelManagerApp(wx.App):
    """模型管理器应用程序"""
    
    def __init__(self):
        super().__init__()
        self.frame = None
        
    def OnInit(self):
        """应用程序初始化"""
        self.frame = ModelManagerFrame()
        return True
        
    def open(self):
        """打开模型管理器界面"""
        # 确保应用已经初始化
        if not self.frame:
            # 如果还没有初始化，先初始化
            if not self.OnInit():
                return False
                
        self.frame.Show()
        self.frame.Raise()
        return True

# 使用示例和替代方案
if __name__ == "__main__":
    # 方案1: 修复后的版本
    app = ModelManagerApp()
    app.open()
    app.MainLoop()
    
    # 方案2: 更推荐的标准用法
    # app = ModelManagerApp()
    # app.MainLoop()  # 这会自动调用OnInit并显示窗口
    
    # 方案3: 直接创建窗口（最简单）
    # app = wx.App()
    # frame = ModelManagerFrame()
    # frame.Show()
    # app.MainLoop()