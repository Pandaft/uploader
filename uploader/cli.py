import click
from .cowtransfer import CowUploader


@click.group()
def cli():
    """uploader"""
    pass


@cli.command()
@click.option("--authorization", type=str, prompt="用户 authorization", help="用户 authorization", required=True)
@click.option("--remember_mev2", type=str, prompt="用户 remember-mev2", help="用户 remember-mev2", required=True)
@click.option("--upload_path", type=str, prompt="待上传文件或目录路径", help="待上传文件或目录路径", required=True)
@click.option("--folder_name", type=str, prompt="文件夹名称", help="文件夹名称", default="")
@click.option("--title", type=str, prompt="传输标题", help="传输标题", default="")
@click.option("--message", type=str, prompt="传输描述", help="传输描述", default="")
@click.option("--valid_days", type=int, prompt="传输有效期（天）", help="传输有效期（天）", default=7, show_default=True)
@click.option("--chunk_size", type=int, prompt="分块大小（字节）", help="分块大小（字节）", default=2097152, show_default=True)
@click.option("--threads", type=int, prompt="上传并发数", help="上传并发数", default=5, show_default=True)
def cow(authorization, remember_mev2, upload_path, folder_name, title, message, valid_days, chunk_size, threads):
    """奶牛快传"""
    thread = CowUploader(authorization, remember_mev2, upload_path, folder_name,
                         title, message, valid_days, chunk_size, threads)
    if thread.start_upload():
        click.echo(f"链接：{thread.upload_info.get('transfer_url')}\n"
                   f"口令：{thread.upload_info.get('transfer_code')}")
    else:
        click.echo(f"上传失败，{thread.err}")
    return thread


if __name__ == "__main__":
    cli()
