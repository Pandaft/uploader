# CowUploader

批量上传文件到 [奶牛快传](https://cowtransfer.com/) ，支持分块并发上传。

<br />

## 使用

### 🖥️ 命令行

📌 计划未来支持。

### 🖥️ 源码

1. 导入此仓库中的 `CowUpload/uploader.py` ：

```
from uploader import CowUploader
```

2. 创建对象并执行上传：

```
ul = CowUploader(
    authorization="___",    # 用户 authorization
    remember_mev2="___",    # 用户 remember-mev2
    upload_path="./test/",  # 待上传文件或目录路径，如果是目录将上传该目录里的所有文件
    valid_days=7,           # 传输有效期（单位：天数，默认 7 天）
    chunk_size=2097152,     # 分块大小（单位：字节，默认 2097152 字节，即 2 MB）
    threads=5               # 上传线程数（默认 5）
)
ul.start_upload()  # 执行上传
```

3. 等待上传完成。

<br />

## 缘由

一直在用着 [transfer](https://github.com/Mikubill/transfer) 但是想自己增加些功能，无奈不会 Go 语言，所以想着用 Python 开发，再在此基础上改进。

+ 感谢 [Mikubill](https://github.com/Mikubill/) / [transfer](https://github.com/Mikubill/transfer) ，研究了好几天该项目源码，才得以成功用 Python 复刻部分功能。

+ 感谢 [kitUIN](https://github.com/kitUIN/) / [CowtransferAPI](https://github.com/kitUIN/CowtransferAPI) ，此项目的读取文件和上传（PUT）的主要参考自该项目。

