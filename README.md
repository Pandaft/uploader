# uploader

一个支持多线程、分块并发、批量上传文件的工具，目前仅支持 [奶牛快传（CowTransfer）](https://cowtransfer.com/) ，后续可能会支持更多的网站。

<br />

## 使用

### 🖥️ 命令行

```shell
> uploader cow --help
Usage: uploader cow [OPTIONS]

  奶牛快传

Options:
  --authorization TEXT  用户 authorization  [required]
  --remember_mev2 TEXT  用户 remember-mev2  [required]
  --upload_path TEXT    待上传文件或目录路径  [required]
  --folder_name TEXT    文件夹名称
  --title TEXT          传输标题
  --message TEXT        传输描述
  --valid_days INTEGER  传输有效期（天）  [default: 7]
  --chunk_size INTEGER  分块大小（字节）  [default: 2097152]
  --threads INTEGER     上传并发数  [default: 5]
  --help                Show this message and exit.
```

### 🖥️ 源码

1. 导入此仓库中 `uploader/cowtransfer.py` 的 `CowUploader` 类：

```
from uploader import CowUploader
```

2. 创建对象并执行上传：

```python
upload_thread = CowUploader(
    authorization="___",    # 用户 authorization
    remember_mev2="___",    # 用户 remember-mev2
    upload_path="./test/",  # 待上传文件或目录路径，如果是目录将上传该目录里的所有文件
    folder_name="test",     # 如果含有子文件夹，将所有文件上传至此文件夹中
    title="",               # 传输标题（默认为空）
    message="",             # 传输描述（默认为空）
    valid_days=7,           # 传输有效期（单位：天数，默认 7 天）
    chunk_size=2097152,     # 分块大小（单位：字节，默认 2097152 字节，即 2 MB）
    threads=5               # 上传并发数（默认 5）
)
upload_thread.start()    # 开始上传
# upload_thread.pause()  # 暂停上传
# upload_thread.work()   # 继续上传
upload_thread.join()     # 等待完成（阻塞直至完成）
print(f"链接：{upload_thread.upload_info.get('transfer_url')}\n"
      f"口令：{upload_thread.upload_info.get('transfer_code')}")
```

3. 等待上传完成。

<br />

## 缘由

一直在用着 [transfer](https://github.com/Mikubill/transfer) 但是想自己增加些功能，无奈不会 Go 语言，所以想着用 Python 开发，再在此基础上改进。

+ 感谢 [Mikubill](https://github.com/Mikubill/) / [transfer](https://github.com/Mikubill/transfer) ，研究了好几天该项目源码，才得以成功用 Python 复刻部分功能。

+ 感谢 [kitUIN](https://github.com/kitUIN/) / [CowtransferAPI](https://github.com/kitUIN/CowtransferAPI) ，此项目的读取文件和上传（PUT）的主要参考自该项目。（已更改为 oss2 上传）

