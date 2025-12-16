import discord
from discord import app_commands
from discord.ext import commands
import random
import time

class GridButton(discord.ui.Button):
    def __init__(self, is_target: bool, row: int):
        self.is_target = is_target
        style = discord.ButtonStyle.primary if is_target else discord.ButtonStyle.secondary
        emoji = "⚪" if is_target else "⚫"
        super().__init__(style=style, emoji=emoji, row=row)

    async def callback(self, interaction: discord.Interaction):
        view: AimTrainerView = self.view

        if interaction.user.id != view.user.id:
            await interaction.response.send_message("Ce n'est pas votre partie !", ephemeral=True)
            return

        if self.is_target:
            view.score += 1
            
            if view.score >= view.target_score:
                await view.end_game(interaction, win=True)
            else:
                view.generate_new_grid()
                await interaction.response.edit_message(content=f"Atteignez l'objectif ! Score : **{view.score}/{view.target_score}**", view=view)
        else:
            await interaction.response.send_message("Raté !", ephemeral=True)


class AimTrainerView(discord.ui.View):
    def __init__(self, user: discord.User, target_score: int, timeout_seconds: int):
        super().__init__(timeout=timeout_seconds)
        self.user = user
        self.target_score = target_score
        self.score = 0
        self.timeout_seconds = timeout_seconds
        self.message = None
        self.start_time = time.time()
        self.generate_new_grid()

    def generate_new_grid(self):
        self.clear_items()
        target_pos = random.randint(0, 24)
        for i in range(25):
            row = i // 5
            self.add_item(GridButton(is_target=(i == target_pos), row=row))

    async def end_game(self, interaction: discord.Interaction, win: bool):
        self.stop()
        for item in self.children:
            item.disabled = True
        
        end_time = time.time()
        duration = round(end_time - self.start_time, 2)

        if win:
            message_content = f"🎉 **Gagné !** Vous avez atteint {self.score} clics en {duration} secondes."
        else:
            message_content = f"⌛ **Temps écoulé !** Vous n'avez fait que {self.score}/{self.target_score} clics dans le temps imparti de {self.timeout_seconds} secondes."

        try:
            await interaction.response.edit_message(content=message_content, view=self)
        except discord.NotFound:
            if self.message:
                await self.message.edit(content=message_content, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        
        end_time = time.time()
        duration = round(end_time - self.start_time, 2)
        
        message_content = f"⌛ **Temps écoulé !** Vous avez fait un score de {self.score}/{self.target_score} en {duration} secondes."

        if self.message:
            await self.message.edit(content=message_content, view=self)


class NouveauJeuCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="jeu_reaction", description="Lance un défi de vitesse et de précision.")
    @app_commands.describe(
        duree="Le temps en secondes pour réussir le défi.",
        objectif="Le nombre de clics à atteindre pour gagner."
    )
    async def jeu_reaction(self, interaction: discord.Interaction, duree: int, objectif: int):
        if duree <= 5 or objectif <= 0:
            await interaction.response.send_message("Veuillez choisir des valeurs valides (durée > 5s, objectif > 0).", ephemeral=True)
            return

        view = AimTrainerView(user=interaction.user, target_score=objectif, timeout_seconds=duree)
        start_message = f"**Défi lancé !** Vous avez {duree} secondes pour cliquer {objectif} fois.\nScore : **0/{objectif}**"
        
        await interaction.response.send_message(start_message, view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(NouveauJeuCog(bot))