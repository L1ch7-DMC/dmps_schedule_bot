
import discord
from discord import app_commands, Interaction, Embed
import random
import math
import itertools

class GameCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="roll", description="サイコロを振ります (例: 3d6)")
    @app_commands.describe(dice="サイコロの形式 (例: 3d6)")
    async def roll_dice_slash(self, interaction: Interaction, dice: str):
        try:
            num_dice, num_sides = map(int, dice.lower().split('d'))
            if not (0 < num_dice <= 100 and num_sides > 0):
                await interaction.response.send_message("サイコロの数(1-100)と面の数(1以上)を正しく指定してくれ！", ephemeral=True); return
            rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
            await interaction.response.send_message(f"{interaction.user.mention} が `{dice}` を振ったぞ！\n出目: {', '.join(map(str, rolls))}")
        except ValueError:
            await interaction.response.send_message("サイコロの形式が正しくないぞ！例: `3d6`", ephemeral=True)

    @app_commands.command(name="draw", description="山札からカードを引く確率を計算します。")
    @app_commands.describe(
        deck_size="非公開領域の枚数 (山札の枚数)",
        target_cards="当たりカードの枚数",
        draw_count="引く枚数",
        required_hits="当たりを引く要求枚数 (デフォルト: 1枚以上)"
    )
    async def draw_chance_slash(
        self, interaction: Interaction,
        deck_size: app_commands.Range[int, 1],
        target_cards: app_commands.Range[int, 0],
        draw_count: app_commands.Range[int, 1],
        required_hits: app_commands.Range[int, 1] = 1
    ):
        if not (target_cards <= deck_size and draw_count <= deck_size and required_hits <= target_cards and required_hits <= draw_count):
            await interaction.response.send_message("入力値が不正だぞ。各値の関係性を確認してくれ。", ephemeral=True); return

        try:
            denominator = math.comb(deck_size, draw_count)
            if denominator == 0: raise ValueError("組み合わせが0通りになるぞ。")

            total_probability = 0.0
            for i in range(required_hits, min(draw_count, target_cards) + 1):
                numerator = math.comb(target_cards, i) * math.comb(deck_size - target_cards, draw_count - i)
                total_probability += numerator / denominator
        except ValueError as e:
            await interaction.response.send_message(f"計算エラー: {e}", ephemeral=True); return

        embed = Embed(title="🃏 確率計算結果", color=discord.Color.blue(), description=f"**`{total_probability:.2%}`** の確率で引けるぞ。")
        embed.add_field(name="非公開領域の枚数", value=f"`{deck_size}`枚", inline=True)
        embed.add_field(name="当たりカードの枚数", value=f"`{target_cards}`枚", inline=True)
        embed.add_field(name="引く枚数", value=f"`{draw_count}`枚", inline=True)
        embed.add_field(name="要求枚数", value=f"`{required_hits}`枚以上", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="combo", description="指定した複数種類のカードを同時に引く確率を計算します。")
    @app_commands.describe(deck_size="山札の枚数", draw_count="引く枚数", copies="各カードの採用枚数をカンマ区切りで入力 (例: 4,4,2)")
    async def combo_chance_slash(
        self, interaction: Interaction,
        deck_size: app_commands.Range[int, 1],
        draw_count: app_commands.Range[int, 1],
        copies: str
    ):
        try:
            copies_list = [int(c.strip()) for c in copies.split(',')]
            if not copies_list or any(c <= 0 for c in copies_list): raise ValueError("カード枚数は1以上の整数で入力してくれ。")
        except ValueError as e:
            await interaction.response.send_message(f"カード枚数の入力形式が正しくないぞ。例: `4, 4, 2`\nエラー: {e}", ephemeral=True); return

        if sum(copies_list) > deck_size or draw_count > deck_size:
            await interaction.response.send_message("カードの合計枚数や引く枚数が、山札の枚数を超えているぞ。", ephemeral=True); return

        try:
            N, n, k_list, m = deck_size, draw_count, copies_list, len(copies_list)
            total_combinations = math.comb(N, n)
            union_of_misses_numerator = 0
            
            for i in range(1, m + 1):
                for subset_indices in itertools.combinations(range(m), i):
                    sum_of_copies_in_subset = sum(k_list[j] for j in subset_indices)
                    term_numerator = math.comb(N - sum_of_copies_in_subset, n) if N - sum_of_copies_in_subset >= n else 0
                    union_of_misses_numerator += term_numerator if (i % 2) == 1 else -term_numerator
            
            favorable_combinations = total_combinations - union_of_misses_numerator
            probability = favorable_combinations / total_combinations if total_combinations > 0 else 0.0
        except (ValueError, TypeError) as e:
            await interaction.response.send_message(f"計算エラーが発生しました: {e}", ephemeral=True); return

        card_fields_text = [f"カード{chr(65+i)}: `{c}`枚" for i, c in enumerate(copies_list)]
        embed = Embed(title="🃏 コンボ確率計算結果", color=discord.Color.green(), description=f"**`{probability:.2%}`** の確率で、指定した**{m}種類**のカードを全て1枚以上引けるぞ。")
        embed.add_field(name="山札の枚数", value=f"`{deck_size}`枚", inline=True)
        embed.add_field(name="引く枚数", value=f"`{draw_count}`枚", inline=True)
        embed.add_field(name="各カードの枚数", value="\n".join(card_fields_text), inline=False)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GameCog(bot))
