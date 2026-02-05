
from discord import Interaction
from discord.app_commands import AppCommandError, MissingAnyRole
from discord.ext import commands

class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # bot.tree.error デコレータはCog内では直接使えないため、リスナーとして追加
        self.bot.tree.on_error = self.on_app_command_error

    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError):
        """スラッシュコマンドのエラーを処理するグローバルハンドラ"""
        if isinstance(error, MissingAnyRole):
            await interaction.response.send_message("このコマンドを実行する権限がないぞ！", ephemeral=True)
        else:
            # 予期しないエラーはコンソールに出力
            print(f"An unhandled app command error occurred: {error}")
            # ユーザーには汎用的なメッセージを返す
            if not interaction.response.is_done():
                await interaction.response.send_message("コマンドの実行中に予期せぬエラーが発生したぞ。", ephemeral=True)
            else:
                await interaction.followup.send("コマンドの実行中に予期せぬエラーが発生したぞ。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
