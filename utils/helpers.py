import re
import discord
from discord.ext import commands

def format_emojis(text: str, bot_instance: commands.Bot) -> str:
    """
    テキスト内の :emoji_name: 形式の文字列を、ボットが利用可能なカスタム絵文字に置換する。
    """
    # :word: というパターンの文字列をすべて見つける
    potential_emoji_names = re.findall(r':(\w+):', text)
    if not potential_emoji_names:
        return text

    # ボットがアクセスできる全絵文字の 名前->絵文字オブジェクト の辞書を作成
    emoji_map = {emoji.name: str(emoji) for emoji in bot_instance.emojis}

    # 見つかった絵文字名を置換していく
    for name in potential_emoji_names:
        if name in emoji_map:
            text = text.replace(f':{name}:', emoji_map[name])
    
    return text