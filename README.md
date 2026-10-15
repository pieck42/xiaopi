# 小皮 Xiaopi

面向客厅电视场景的像素桌面伙伴，支持小狐狸和小龙两种形象。计划通过语音与 Cindy 连接，成为 Cindy 的桌面化身。

当前已包含 Windows 透明桌面原型、状态动画和单文件网页预览。语音与 Cindy 连接尚未实现，界面中的对话和状态为模拟演示。

## 运行

需要 Python 3、Tkinter 和 Pillow：

```powershell
python -m pip install -r requirements.txt
python xiaopi.py
```

双击形象切换小狐狸/小龙，右键打开功能菜单。完整操作见 [使用说明](使用说明.md)。`启动小皮.vbs` 从 PATH 查找 `pythonw.exe`；无法启动时可使用上述命令。

打开 `小皮预览.html` 可查看无需安装依赖的网页演示。修改模板或素材后，运行 `python build_preview.py` 重建预览。

## 设计

- [动作设计](动作设计.md)
- [Cindy 连接层与模块边界](docs/Cindy连接层与模块边界.md)

`settings.json` 是个人设备设置，首次启动可自动生成，不纳入版本管理。
