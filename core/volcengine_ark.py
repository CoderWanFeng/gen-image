"""
火山引擎 ARK 图像生成 API Python 工具
支持文生图和图生图
"""

import os
import base64
import json
from pathlib import Path
from typing import Optional, List, Union

try:
    from volcenginesdkarkruntime import Ark
except ImportError:
    print("请安装方舟SDK: pip install 'volcengine-python-sdk[ark]'")
    raise


class VolcengineARK:
    """火山引擎 ARK 图像生成 API 封装"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
    ):
        """
        初始化火山引擎 ARK 客户端

        Args:
            api_key: API Key，默认从环境变量 ARK_API_KEY 获取
            base_url: API 地址，默认北京区域
        """
        self.api_key = api_key or os.getenv("ARK_API_KEY")
        self.base_url = base_url

        if not self.api_key:
            raise ValueError("请提供 API Key，或设置环境变量 ARK_API_KEY")

        self.client = Ark(base_url=self.base_url, api_key=self.api_key)

    def generate_image(
        self,
        prompt: str,
        model: str = "doubao-seedream-5-0-260128",
        image: Union[str, List[str], None] = None,
        sequential_image_generation: str = "disabled",
        response_format: str = "url",
        size: str = "2K",
        watermark: bool = True,
    ) -> str:
        """
        文生图或图生图

        Args:
            prompt: 文本描述
            model: 模型名称，默认 doubao-seedream-5-0-260128
            image: 输入图片，支持以下格式：
                   - None: 文生图
                   - str: 单张图片（URL 或 data URI）
                   - List[str]: 多张图片（URL 或 data URI），图生图时传入多张可提升一致性
            sequential_image_generation: 顺序生成，"disabled" 或 "enabled"
            response_format: 返回格式 "url" 或 "base64"
            size: 图片尺寸，如 "2K"、"2560x1920" 等
            watermark: 是否添加水印

        Returns:
            生成的图片 URL 或 Base64 字符串
        """
        kwargs = {
            "model": model,
            "prompt": prompt,
            "sequential_image_generation": sequential_image_generation,
            "response_format": response_format,
            "size": size,
            "stream": False,
            "watermark": watermark,
        }

        if image:
            kwargs["image"] = image

        try:
            response = self.client.images.generate(**kwargs)
            return response.data[0].url if response_format == "url" else response.data[0].b64_json
        except Exception as e:
            raise RuntimeError(f"图像生成失败: {e}")

    def download_image(self, url: str, save_path: str) -> str:
        """下载图片到本地"""
        import urllib.request

        urllib.request.urlretrieve(url, save_path)
        return save_path


def save_image(data: str, output_path: str) -> str:
    """
    保存图片数据到文件

    Args:
        data: Base64 字符串或 URL
        output_path: 保存路径

    Returns:
        保存的文件路径
    """
    import urllib.request

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if data.startswith("http"):
        urllib.request.urlretrieve(data, output_path)
    else:
        img_data = base64.b64decode(data)
        with open(output_path, "wb") as f:
            f.write(img_data)

    return output_path


# ============================================================================
# 便捷函数
# ============================================================================
def txt2img(
    prompt: str,
    output: str = "output.png",
    model: str = "doubao-seedream-5-0-260128",
    size: str = "2K",
    watermark: bool = True,
    api_key: str = None,
) -> str:
    """
    文生图便捷函数

    Args:
        prompt: 文本描述
        output: 输出文件路径
        model: 模型名称
        size: 图片尺寸
        watermark: 是否添加水印
        api_key: API Key

    Returns:
        生成图片的路径
    """
    client = VolcengineARK(api_key=api_key)
    result = client.generate_image(
        prompt=prompt,
        model=model,
        size=size,
        watermark=watermark,
    )
    return save_image(result, output)


def img2img(
    input_image: str,
    prompt: str,
    output: str = "output.png",
    model: str = "doubao-seedream-5-0-260128",
    size: str = "2K",
    watermark: bool = True,
    api_key: str = None,
) -> str:
    """
    图生图便捷函数

    Args:
        input_image: 输入图片 URL
        prompt: 文本描述
        output: 输出文件路径
        model: 模型名称
        size: 图片尺寸
        watermark: 是否添加水印
        api_key: API Key

    Returns:
        生成图片的路径
    """
    client = VolcengineARK(api_key=api_key)
    result = client.generate_image(
        prompt=prompt,
        model=model,
        image=input_image,
        size=size,
        watermark=watermark,
    )
    return save_image(result, output)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="火山引擎 ARK 图像生成工具")
    parser.add_argument("--mode", "-m", choices=["txt2img", "img2img"], default="txt2img", help="模式")
    parser.add_argument("--prompt", "-p", help="文本描述（必填）")
    parser.add_argument("--input", "-i", help="输入图片 URL（图生图模式必填）")
    parser.add_argument("--output", "-o", default="output.png", help="输出文件路径")
    parser.add_argument("--model", default="doubao-seedream-5-0-260128", help="模型名称")
    parser.add_argument("--size", "-s", default="2K", help="图片尺寸（默认2K）")
    parser.add_argument("--api-key", help="API Key")

    args = parser.parse_args()

    if args.mode == "txt2img":
        if not args.prompt:
            print("错误：文生图模式需要提供 --prompt 参数")
            exit(1)
        result = txt2img(
            prompt=args.prompt,
            output=args.output,
            model=args.model,
            size=args.size,
            api_key=args.api_key,
        )
        print(f"生成成功: {result}")
    else:
        if not args.input:
            print("错误：图生图模式需要提供 --input 参数")
            exit(1)
        if not args.prompt:
            print("错误：图生图模式需要提供 --prompt 参数")
            exit(1)
        result = img2img(
            input_image=args.input,
            prompt=args.prompt,
            output=args.output,
            model=args.model,
            size=args.size,
            api_key=args.api_key,
        )
        print(f"生成成功: {result}")
