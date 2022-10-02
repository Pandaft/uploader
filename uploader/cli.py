import click
from .cowtransfer import CowUploader
from .musetransfer import MuseUploader


@click.group()
def cli():
    """uploader - v0.1.4"""
    pass


@cli.command()
@click.option("--authorization", type=str, prompt="用户 authorization", help="用户 authorization", required=True)
@click.option("--remember_mev2", type=str, prompt="用户 remember-mev2", help="用户 remember-mev2", required=True)
@click.option("--upload_path", type=str, prompt="待上传文件或目录路径", help="待上传文件或目录路径", required=True)
@click.option("--folder_name", type=str, help="文件夹名称", default="")
@click.option("--title", type=str, help="传输标题", default="")
@click.option("--message", type=str, help="传输描述", default="")
@click.option("--valid_days", type=int, help="传输有效期（天）", default=7, show_default=True)
@click.option("--chunk_size", type=int, help="分块大小（字节）", default=2097152, show_default=True)
@click.option("--threads", type=int, help="上传并发数", default=5, show_default=True)
def cow(authorization, remember_mev2, upload_path, folder_name, title, message, valid_days, chunk_size, threads):
    """CowTransfer - 奶牛快传"""
    thread = CowUploader(authorization, remember_mev2, upload_path, folder_name,
                         title, message, valid_days, chunk_size, threads)
    if thread.start_upload():
        click.echo(f"链接：{thread.upload_info.get('transfer_url')}\n"
                   f"口令：{thread.upload_info.get('transfer_code')}")
    else:
        click.echo(f"上传失败，{thread.err}")
    return thread


@cli.command()
@click.option("--client_id", type=str, prompt="client_id", help="client_id", required=True)
@click.option("--client_key", type=str, prompt="client_key", help="client_key", required=True)
@click.option("--upload_path", type=str, prompt="待上传文件或目录路径", help="待上传文件或目录路径", required=True)
@click.option("--title", type=str, help="分享链接的标题", default="untitled")
@click.option("--password", type=str, help="分享链接的密码（4位数字，默认无密码）", default="")
@click.option("--valid_days", type=int, help="传输有效期（天）", default=7, show_default=True)
@click.option("--chunk_size", type=int, help="分块大小（字节）", default=2097152, show_default=True)
@click.option("--threads", type=int, help="上传并发数", default=5, show_default=True)
def muse(client_id, client_key, upload_path, title, password, valid_days, chunk_size, threads):
    """MuseTransfer"""
    thread = MuseUploader(client_id, client_key, upload_path, title,
                          password, valid_days, chunk_size, threads)
    if thread.start_upload():
        click.echo(f"链接：{thread.upload_info.get('transfer_url')}")
    else:
        click.echo(f"上传失败，{thread.err}")
    return thread


if __name__ == "__main__":
    cli()
