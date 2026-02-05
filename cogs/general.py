import discord
from discord.ext import commands
from discord import Interaction, app_commands, Embed
import random
import math
import itertools

class General(commands.Cog):
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

    @app_commands.command(name="note", description="メンバー紹介noteのURLを送信します。")
    async def note_slash(self, interaction: Interaction):
        await interaction.response.send_message("GTVメンバー紹介noteだ！\nhttps://note.com/koresute_0523/n/n1b3bf9754432")

    @app_commands.command(name="draw", description="山札からカードを引く確率を計算します。")
    @app_commands.describe(
        deck_size="非公開領域の枚数 (山札の枚数)",
        target_cards="当たりカードの枚数",
        draw_count="引く枚数",
        required_hits="当たりを引く要求枚数 (デフォルト: 1枚以上)"
    )
    async def draw_chance_slash(
        self,
        interaction: Interaction,
        deck_size: app_commands.Range[int, 1],
        target_cards: app_commands.Range[int, 0],
        draw_count: app_commands.Range[int, 1],
        required_hits: app_commands.Range[int, 1] = 1
    ):
        # --- 1. 先にバリデーションを行う ---
        if target_cards > deck_size:
            await interaction.response.send_message("当たりカードの枚数が、非公開領域の枚数を超えているぞ。", ephemeral=True)
            return
        if draw_count > deck_size:
            await interaction.response.send_message("引く枚数が、非公開領域の枚数を超えているぞ。", ephemeral=True)
            return
        if required_hits > target_cards:
            await interaction.response.send_message("要求枚数が、当たりカードの枚数を超えているぞ。", ephemeral=True)
            return
        if required_hits > draw_count:
            await interaction.response.send_message("要求枚数が、引く枚数を超えているぞ。", ephemeral=True)
            return

        # --- 確率計算 ---
        try:
            # 分母: C(N, n)
            denominator = math.comb(deck_size, draw_count)
            if denominator == 0:
                raise ValueError("引く枚数が非公開領域の枚数を超えているため、組み合わせを計算できないぞ。")

            # required_hits 枚以上引く確率 P(X >= k) を計算
            sum_range_direct = min(draw_count, target_cards) - required_hits + 1
            sum_range_complement = required_hits

            if sum_range_direct < sum_range_complement:
                total_probability = 0.0
                loop_end = min(draw_count, target_cards)
                for i in range(required_hits, loop_end + 1):
                    numerator = math.comb(target_cards, i) * math.comb(deck_size - target_cards, draw_count - i)
                    total_probability += numerator / denominator
            else:
                complement_prob = 0.0
                loop_end = min(required_hits - 1, draw_count, target_cards)
                for i in range(loop_end + 1):
                    numerator = math.comb(target_cards, i) * math.comb(deck_size - target_cards, draw_count - i)
                    complement_prob += numerator / denominator
                total_probability = 1.0 - complement_prob
        except ValueError as e:
            await interaction.response.send_message(f"計算エラー: {e}", ephemeral=True)
            return

        # --- 結果をEmbedで表示 ---
        embed = Embed(title="🃏 確率計算結果", color=discord.Color.blue())
        embed.description = f"**`{total_probability:.2%}`** の確率で引けるぞ。"
        
        embed.add_field(name="非公開領域の枚数", value=f"`{deck_size}`枚", inline=True)
        embed.add_field(name="当たりカードの枚数", value=f"`{target_cards}`枚", inline=True)
        embed.add_field(name="引く枚数", value=f"`{draw_count}`枚", inline=True)
        embed.add_field(name="要求枚数", value=f"`{required_hits}`枚以上", inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="combo", description="指定した複数種類のカードを同時に引く確率を計算します。")
    @app_commands.describe(
        deck_size="山札の枚数",
        draw_count="引く枚数",
        copies="各カードの採用枚数をカンマ区切りで入力 (例: 4,4,2)"
    )
    @app_commands.rename(draw_count='引く枚数')
    async def combo_chance_slash(
        self,
        interaction: Interaction,
        deck_size: app_commands.Range[int, 1],
        draw_count: app_commands.Range[int, 1],
        copies: str
    ):
        # --- 1. Parse and validate input ---
        try:
            copies_list = [int(c.strip()) for c in copies.split(',')]
            if not copies_list:
                raise ValueError("枚数が入力されていません。")
            if any(c <= 0 for c in copies_list):
                raise ValueError("カードの枚数は1以上の整数である必要があります。")
        except ValueError as e:
            await interaction.response.send_message(f"カード枚数の入力形式が正しくないぞ。\n例: `4, 4, 2`\nエラー: {e}", ephemeral=True)
            return

        # --- More Validation ---
        if sum(copies_list) > deck_size:
            await interaction.response.send_message("各カードの合計枚数が、山札の枚数を超えています。", ephemeral=True)
            return
        if draw_count > deck_size:
            await interaction.response.send_message("引く枚数が、山札の枚数を超えています。", ephemeral=True)
            return

        # --- 2. Probability Calculation (Inclusion-Exclusion) ---
        try:
            N = deck_size
            n = draw_count
            k_list = copies_list
            m = len(k_list)

            total_combinations = math.comb(N, n)
            
            # This is the numerator for P(not A or not B or ...)
            union_of_misses_numerator = 0
            
            # Iterate through all non-empty subsets of card types
            for i in range(1, m + 1):
                # Generate all combinations of indices of size i
                for subset_indices in itertools.combinations(range(m), i):
                    sum_of_copies_in_subset = sum(k_list[j] for j in subset_indices)
                    
                    if N - sum_of_copies_in_subset < n:
                        term_numerator = 0
                    else:
                        term_numerator = math.comb(N - sum_of_copies_in_subset, n)

                    # Add or subtract based on the size of the subset (inclusion-exclusion)
                    if (i % 2) == 1: # i is the size of the subset
                        union_of_misses_numerator += term_numerator
                    else:
                        union_of_misses_numerator -= term_numerator
            
            # Favorable = Total - (ways to miss at least one card type)
            favorable_combinations = total_combinations - union_of_misses_numerator
            
            if total_combinations == 0:
                probability = 0.0
            else:
                probability = favorable_combinations / total_combinations

        except (ValueError, TypeError) as e:
            await interaction.response.send_message(f"計算エラーが発生しました: {e}", ephemeral=True)
            return

        # --- 3. Result Display ---
        card_fields_text = []
        for i, c in enumerate(copies_list):
            card_fields_text.append(f"カード{chr(65+i)}: `{c}`枚")

        embed = Embed(title="🃏 コンボ確率計算結果", color=discord.Color.green())
        embed.description = f"**`{probability:.2%}`** の確率で、指定した**{m}種類**のカードを全て1枚以上引けるぞ。"
        
        embed.add_field(name="山札の枚数", value=f"`{deck_size}`枚", inline=True)
        embed.add_field(name="引く枚数", value=f"`{draw_count}`枚", inline=True)
        embed.add_field(name="各カードの枚数", value="\n".join(card_fields_text), inline=False)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))