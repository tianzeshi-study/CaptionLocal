# -*- coding: UTF-8 -*-
import wx
import os
import threading
from typing import List, Tuple, Optional
import sys
import winsound  # Windows sound API for audio notifications

# Assume modelDownloader.py is in the same directory
try:
    from .modelDownloader import download_models_multithreaded, ensure_models_directory, get_model_file_paths
except ImportError as e:
    print(f"Error importing modelDownloader: {e}")
    print("Please ensure modelDownloader.py is in the same directory")
    sys.exit(1)

class AdvancedSettingsDialog(wx.Dialog):
    """Advanced Settings Dialog"""
    
    def __init__(self, parent, model_name="Xenova/vit-gpt2-image-captioning", 
                 files_list=None, resolve_path="/resolve/main", use_mirror=False):
        super().__init__(parent, title="Advanced Settings", size=(500, 400),
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
        """Initialize interface"""
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Create notebook control for grouping
        notebook = wx.Notebook(self)
        
        # Model configuration page
        model_panel = wx.Panel(notebook)
        model_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Model name
        model_sizer.Add(wx.StaticText(model_panel, label="Model Name:"), 0, wx.ALL, 5)
        self.model_name_ctrl = wx.TextCtrl(model_panel, value=self.model_name, size=(400, -1))
        model_sizer.Add(self.model_name_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        
        # Resolve path
        model_sizer.Add(wx.StaticText(model_panel, label="Resolve Path:"), 0, wx.ALL, 5)
        self.resolve_path_ctrl = wx.TextCtrl(model_panel, value=self.resolve_path, size=(400, -1))
        model_sizer.Add(self.resolve_path_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        
        # Use mirror
        self.use_mirror_cb = wx.CheckBox(model_panel, label="Use HuggingFace Mirror")
        self.use_mirror_cb.SetValue(self.use_mirror)
        model_sizer.Add(self.use_mirror_cb, 0, wx.ALL, 5)
        
        model_panel.SetSizer(model_sizer)
        notebook.AddPage(model_panel, "Model Config")
        
        # File list page
        files_panel = wx.Panel(notebook)
        files_sizer = wx.BoxSizer(wx.VERTICAL)
        
        files_sizer.Add(wx.StaticText(files_panel, label="Files to Download:"), 0, wx.ALL, 5)
        
        # File list control
        self.files_listbox = wx.ListBox(files_panel, choices=self.files_list, 
                                       style=wx.LB_MULTIPLE | wx.LB_HSCROLL)
        # Select all files by default
        for i in range(len(self.files_list)):
            self.files_listbox.SetSelection(i)
        files_sizer.Add(self.files_listbox, 1, wx.ALL | wx.EXPAND, 5)
        
        # File operation buttons
        file_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.add_file_btn = wx.Button(files_panel, label="Add File")
        self.remove_file_btn = wx.Button(files_panel, label="Remove File")
        file_btn_sizer.Add(self.add_file_btn, 0, wx.ALL, 2)
        file_btn_sizer.Add(self.remove_file_btn, 0, wx.ALL, 2)
        files_sizer.Add(file_btn_sizer, 0, wx.ALL | wx.CENTER, 5)
        
        files_panel.SetSizer(files_sizer)
        notebook.AddPage(files_panel, "File List")
        
        main_sizer.Add(notebook, 1, wx.ALL | wx.EXPAND, 10)
        
        # Dialog buttons
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK, "OK")
        cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.CENTER, 10)
        
        self.SetSizer(main_sizer)
        
    def _bind_events(self):
        """Bind events"""
        self.add_file_btn.Bind(wx.EVT_BUTTON, self.on_add_file)
        self.remove_file_btn.Bind(wx.EVT_BUTTON, self.on_remove_file)
        
    def on_add_file(self, event):
        """Add file"""
        dlg = wx.TextEntryDialog(self, "Enter file path:", "Add File")
        if dlg.ShowModal() == wx.ID_OK:
            file_path = dlg.GetValue().strip()
            if file_path and file_path not in self.files_list:
                self.files_list.append(file_path)
                self.files_listbox.Append(file_path)
                # Select the newly added file
                self.files_listbox.SetSelection(len(self.files_list) - 1)
        dlg.Destroy()
        
    def on_remove_file(self, event):
        """Remove file"""
        selection = self.files_listbox.GetSelections()
        if selection != wx.NOT_FOUND:
            for s in sorted(selection, reverse=True):
                self.files_list.pop(s)
                self.files_listbox.Delete(s)
            
    def get_settings(self) -> dict:
        """Get settings"""
        # Get selected files
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

class SoundNotification:
    """Sound notification manager using Windows standard library"""
    
    @staticmethod
    def play_start():
        """Play download start sound"""
        try:
            # Play system information sound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception as e:
            print(e)
            pass  # Silently fail if sound unavailable
    
    @staticmethod
    def play_success():
        """Play success sound"""
        try:
            # Play system default sound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception as e:
            print(e)
            pass
    
    @staticmethod
    def play_error():
        """Play error sound"""
        try:
            # Play system error sound
            winsound.MessageBeep(winsound.MB_ICONHAND)
        except Exception as e:
            print(e)
            pass
    
    @staticmethod
    def play_warning():
        """Play warning sound"""
        try:
            # Play system warning sound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception as e:
            print(e)
            pass

class ModelManagerFrame(wx.Frame):
    """Model Manager Main Frame"""
    
    def __init__(self):
        super().__init__(None, title="Model Manager", size=(600, 450))
        
        # Default settings
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
        
        # Download related
        self.download_thread = None
        self.download_cancelled = False
        
        self._init_ui()
        self._init_default_path()
        self._bind_events()
        
        # Center display
        self.Centre()
        
    def _init_ui(self):
        """Initialize user interface"""
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Title
        title_text = wx.StaticText(panel, label="Model Download Manager")
        title_font = title_text.GetFont()
        title_font.PointSize += 4
        title_font = title_font.Bold()
        title_text.SetFont(title_font)
        main_sizer.Add(title_text, 0, wx.ALL | wx.CENTER, 15)
        
        # Download path selection
        path_box = wx.StaticBoxSizer(wx.StaticBox(panel, label="Download Settings"), wx.VERTICAL)
        
        path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        path_sizer.Add(wx.StaticText(panel, label="Download Path:"), 0, wx.ALL | wx.CENTER, 5)
        
        self.path_ctrl = wx.TextCtrl(panel, size=(350, -1))
        path_sizer.Add(self.path_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        
        self.browse_btn = wx.Button(panel, label="Browse...")
        path_sizer.Add(self.browse_btn, 0, wx.ALL, 5)
        
        path_box.Add(path_sizer, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(path_box, 0, wx.ALL | wx.EXPAND, 10)
        
        # Model information display
        info_box = wx.StaticBoxSizer(wx.StaticBox(panel, label="Model Information"), wx.VERTICAL)
        
        self.model_info_text = wx.StaticText(panel, label=f"Model: {self.model_name}")
        info_box.Add(self.model_info_text, 0, wx.ALL, 5)
        
        self.files_info_text = wx.StaticText(panel, label=f"File Count: {len(self.files_to_download)}")
        info_box.Add(self.files_info_text, 0, wx.ALL, 5)
        
        main_sizer.Add(info_box, 0, wx.ALL | wx.EXPAND, 10)
        
        # Operation buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.advanced_btn = wx.Button(panel, label="Advanced Settings...")
        btn_sizer.Add(self.advanced_btn, 0, wx.ALL, 5)
        
        btn_sizer.AddStretchSpacer(1)
        
        self.download_btn = wx.Button(panel, label="Start Download", size=(120, 35))
        self.download_btn.SetBackgroundColour(wx.Colour(0, 120, 215))
        self.download_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        btn_sizer.Add(self.download_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)
        
        # Status bar
        self.status_text = wx.StaticText(panel, label="Ready")
        main_sizer.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 10)
        
        # Log area
        log_box = wx.StaticBoxSizer(wx.StaticBox(panel, label="Download Log"), wx.VERTICAL)
        self.log_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                   size=(550, 150))
        log_box.Add(self.log_text, 1, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(log_box, 1, wx.ALL | wx.EXPAND, 10)
        
        panel.SetSizer(main_sizer)
        
    def _init_default_path(self):
        """Initialize default path"""
        try:
            default_path = ensure_models_directory()
            self.download_path = default_path
            self.path_ctrl.SetValue(default_path)
            self.log(f"Default download path: {default_path}")
        except Exception as e:
            self.log(f"Failed to initialize path: {e}")
            
    def _bind_events(self):
        """Bind events"""
        self.browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_path)
        self.advanced_btn.Bind(wx.EVT_BUTTON, self.on_advanced_settings)
        self.download_btn.Bind(wx.EVT_BUTTON, self.on_download)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        # Bind ESC key to close
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)
        
    def on_key_down(self, event):
        """Handle key press events"""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
        else:
            event.Skip()
        
    def log(self, message: str):
        """Add log information"""
        wx.CallAfter(self._log_safe, message)
        
    def _log_safe(self, message: str):
        """Thread-safe log addition"""
        if not self.IsBeingDeleted():
            self.log_text.AppendText(f"{message}\n")
            self.log_text.SetInsertionPointEnd()
            
    def update_status(self, status: str):
        """Update status"""
        wx.CallAfter(self._update_status_safe, status)
        
    def _update_status_safe(self, status: str):
        """Thread-safe status update"""
        if not self.IsBeingDeleted():
            self.status_text.SetLabel(status)
            
    def update_progress(self, file_name: str, downloaded: int, total: int, progress_percent: float):
        self.log(f"file: {file_name}  progress: {progress_percent:.2f}%")
    
    def on_browse_path(self, event):
        """Browse path"""
        dlg = wx.DirDialog(self, "Select Download Directory", defaultPath=self.download_path)
        if dlg.ShowModal() == wx.ID_OK:
            self.download_path = dlg.GetPath()
            self.path_ctrl.SetValue(self.download_path)
            self.log(f"Download path changed to: {self.download_path}")
        dlg.Destroy()
        
    def on_advanced_settings(self, event):
        """Advanced settings"""
        dlg = AdvancedSettingsDialog(self, self.model_name, self.files_to_download,
                                   self.resolve_path, self.use_mirror)
        if dlg.ShowModal() == wx.ID_OK:
            settings = dlg.get_settings()
            self.model_name = settings['model_name']
            self.files_to_download = settings['files_to_download']
            self.resolve_path = settings['resolve_path']
            self.use_mirror = settings['use_mirror']
            
            # Update display information
            self.model_info_text.SetLabel(f"Model: {self.model_name}")
            self.files_info_text.SetLabel(f"File Count: {len(self.files_to_download)}")
            
            mirror_info = " (using mirror)" if self.use_mirror else ""
            self.log(f"Settings updated: {self.model_name}{mirror_info}, {len(self.files_to_download)} files")
            
        dlg.Destroy()
        
    def on_download(self, event):
        """Start download"""
        if self.download_thread and self.download_thread.is_alive():
            self.log("Download in progress...")
            return
            
        if not self.files_to_download:
            # Use gentle notification instead of message box
            SoundNotification.play_error()
            self.log("❌ Error: Please select files to download in Advanced Settings")
            self.update_status("Error: No files selected")
            return
            
        # Disable download button
        self.download_btn.Enable(False)
        self.download_cancelled = False
        
        # Play start sound
        SoundNotification.play_start()
        
        # Start download thread
        self.download_thread = threading.Thread(target=self._download_worker)
        self.download_thread.daemon = True
        self.download_thread.start()
        
    def _download_worker(self):
        """Download worker thread"""
        try:
            self.update_status("Downloading...")
            self.log("Starting model file download...")
            
            # Determine remote host
            remote_host = "hf-mirror.com" if self.use_mirror else "huggingface.co"
            
            self.log(f"Remote host: {remote_host}")
            self.log(f"Model name: {self.model_name}")
            self.download_path = self.path_ctrl.GetValue()
            self.log(f"Download path: {self.download_path}")
            self.log(f"File count: {len(self.files_to_download)}")
            self.log("Downloading... please wait")
            
            # Call download function
            successful, failed = download_models_multithreaded(
                models_dir=self.download_path,
                remote_host=remote_host,
                model_name=self.model_name,
                files_to_download=self.files_to_download,
                resolve_path=self.resolve_path,
                max_workers=4,
                progress_callback=self.update_progress
            )
            
            # Process results
            if not self.download_cancelled:
                self._handle_download_result(successful, failed)
                
        except Exception as e:
            self.log(f"Error during download: {e}")
            self.update_status("Download failed")
            SoundNotification.play_error()
        finally:
            wx.CallAfter(self._download_finished)
            
    def _handle_download_result(self, successful: List[str], failed: List[str]):
        """Handle download results"""
        total = len(successful) + len(failed)
        
        if not failed:
            # All successful
            self.log(f"✅ All files downloaded successfully! ({len(successful)}/{total})")
            self.update_status("Download completed")
            SoundNotification.play_success()
        elif not successful:
            # All failed
            self.log(f"❌ All files download failed! ({len(failed)}/{total})")
            self.log(f"Failed files: {', '.join(failed)}")
            self.update_status("Download failed")
            SoundNotification.play_error()
        else:
            # Partial success
            self.log(f"⚠️ Partial download success ({len(successful)}/{total})")
            self.log(f"Successful: {len(successful)} files")
            self.log(f"Failed: {len(failed)} files - {', '.join(failed)}")
            self.update_status("Partially completed")
            SoundNotification.play_warning()
            
    def _download_finished(self):
        """Clean up after download completion"""
        self.download_btn.Enable(True)
        
    def on_close(self, event):
        """Close event"""
        if self.download_thread and self.download_thread.is_alive():
            self.download_cancelled = True
            dlg = wx.MessageDialog(self, "Download is in progress. Are you sure you want to exit?", "Confirm Exit", 
                                 wx.YES_NO | wx.ICON_QUESTION)
            if dlg.ShowModal() != wx.ID_YES:
                dlg.Destroy()
                return
            dlg.Destroy()
        
        self.Destroy()

class ModelManagerApp(wx.App):
    """Model Manager Application"""
    
    def __init__(self):
        super().__init__()
        self.frame = None
        
    def OnInit(self):
        """Application initialization"""
        self.frame = ModelManagerFrame()
        return True
        
    def open(self):
        """Open model manager interface"""
        # Ensure application is initialized
        if not self.frame:
            # If not initialized yet, initialize first
            if not self.OnInit():
                return False
                
        self.frame.Show()
        self.frame.Raise()
        return True

# Usage examples and alternatives
if __name__ == "__main__":
    # Solution 1: Fixed version
    app = ModelManagerApp()
    app.open()
    app.MainLoop()
    
    # Solution 2: More recommended standard usage
    # app = ModelManagerApp()
    # app.MainLoop()  # This will automatically call OnInit and show window
    
    # Solution 3: Direct window creation (simplest)
    # app = wx.App()
    # frame = ModelManagerFrame()
    # frame.Show()
    # app.MainLoop()