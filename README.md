# uploader

一个支持多线程、分块并发、批量上传文件的工具。

## 支持

- [CowTransfer（奶牛快传）](https://cowtransfer.com/)
- [MuseTransfer](https://musetransfer.com/)

## 用法

参考：[wiki](https://github.com/Aixzk/uploader/wiki)

- 可在 Release 中下载最新编译的对应平台的可执行文件，通过命令行的方式使用。

- 也可通过实例化源码的上传类进行灵活的上传控制（暂停、继续、获取进度信息等）。

## 缘由

一直在用着 [transfer](https://github.com/Mikubill/transfer) 但是想自己增加些功能，无奈不会 Go 语言，所以想着用 Python 开发，再在此基础上改进。

+ 感谢 [Mikubill](https://github.com/Mikubill/) / [transfer](https://github.com/Mikubill/transfer) ，研究了好几天该项目源码，才得以成功用 Python 复刻部分功能。

+ 感谢 [kitUIN](https://github.com/kitUIN/) / [CowtransferAPI](https://github.com/kitUIN/CowtransferAPI) ，此项目的读取文件和上传（PUT）的主要参考自该项目。（已更改为 oss2 上传）

