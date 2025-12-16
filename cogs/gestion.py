import discord
from discord import app_commands
from discord.ext import commands
import copy
import math
from .game_manager import InventoryView, ReserveView



async def user_pouvoir_autocompletion(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    user_inv = interaction.client.get_user_inventory(interaction.user.id)
    choices = list(set([p['nom'] for p in user_inv.get("pouvoirs", [])]))
    return [app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()][:25]

async def user_equipement_autocompletion(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    user_inv = interaction.client.get_user_inventory(interaction.user.id)
    choices = list(set([eq['nom'] for eq in user_inv.get("equipements", [])]))
    return [app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()][:25]

async def intelligent_personnage_autocompletion(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:    
    choices = []    # On vérifie si une partie est en cours, exactement comme dans la commande    
    game_manager_cog = interaction.client.get_cog('GameManagerCog')    
    if game_manager_cog and interaction.channel.id in game_manager_cog.active_games:        
        # Si OUI, on prend les personnages du catalogue global        
        choices = list(interaction.client.catalogue_personnages.keys())    
    else:        # Si NON, on prend les personnages de l'inventaire permanent de l'utilisateur        
        user_inv = interaction.client.get_user_inventory(interaction.user.id)        
        choices = list(set([p['nom'] for p in user_inv.get("personnages", [])]))        
        # Le reste de la fonction est standard    
    return [app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()][:25]

# ... les autres fonctions ...

class GestionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Groupe /equiper ---
    equiper = app_commands.Group(name="equiper", description="Commandes pour équiper personnages, pouvoirs et équipements.")
    
    # Dans cogs/gestion.py

    @equiper.command(name="personnage", description="Place un personnage dans un slot de votre réserve.")
    # On utilise la NOUVELLE autocomplétion
    @app_commands.autocomplete(nom_personnage=intelligent_personnage_autocompletion)
    async def equiper_personnage(self, interaction: discord.Interaction, slot: int, nom_personnage: str):
        # --- DÉBUT DE LA LOGIQUE "INTELLIGENTE" ---
        game_manager_cog = self.bot.get_cog('GameManagerCog')
        if game_manager_cog and interaction.channel.id in game_manager_cog.active_games:
            game_state = game_manager_cog.active_games[interaction.channel.id]
            player_state = game_state['players'].get(interaction.user.id)
            if player_state:
                if not 1 <= slot <= 3:
                    return await interaction.response.send_message("Erreur : Le slot doit être 1, 2, ou 3.", ephemeral=True)
                
                # On pioche dans le catalogue global
                perso_catalogue = self.bot.catalogue_personnages.get(nom_personnage)
                if not perso_catalogue:
                    return await interaction.response.send_message(f"Personnage '{nom_personnage}' introuvable dans le catalogue.", ephemeral=True)

                # On vérifie qu'il n'est pas déjà dans la réserve temporaire
                if any(p and p["nom"].lower() == nom_personnage.lower() for p in player_state["reserve_combat"]):
                    return await interaction.response.send_message(f"**{nom_personnage}** est déjà dans votre réserve de partie.", ephemeral=True)

                perso_copy = copy.deepcopy(perso_catalogue)
                # On initialise proprement le personnage pour la partie
                perso_copy["pouvoirs"] = [None, None, None]
                perso_copy["equipement"] = None
                
                # On modifie la réserve TEMPORAIRE
                player_state["reserve_combat"][slot - 1] = perso_copy
                
                await interaction.response.send_message(f"**{perso_copy['nom']}** a été placé dans le slot {slot} de votre réserve de partie.", ephemeral=True)
                
                # On affiche la réserve mise à jour pour que le joueur voie le résultat
                await game_manager_cog._send_reserve_view_dm(player_state)
                return
        # --- FIN DE LA LOGIQUE "INTELLIGENTE" ---

        # Comportement normal si aucune partie n'est en cours (le code existant)
        if not 1 <= slot <= 3: return await interaction.response.send_message("Erreur : Le slot doit être 1, 2, ou 3.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        perso_a_placer = next((p for p in user_inv["personnages"] if p["nom"].lower() == nom_personnage.lower()), None)
        if not perso_a_placer: return await interaction.response.send_message(f"Vous ne possédez pas '{nom_personnage}'.", ephemeral=True)
        if any(p and p["nom"].lower() == nom_personnage.lower() for p in user_inv["reserve_combat"]): return await interaction.response.send_message(f"**{perso_a_placer['nom']}** est déjà dans votre réserve.", ephemeral=True)
        perso_copy = copy.deepcopy(perso_a_placer)
        perso_copy["pouvoirs"] = [None, None, None]
        perso_copy["equipement"] = None
        user_inv["reserve_combat"][slot - 1] = perso_copy
        self.bot.save_data()
        await interaction.response.send_message(f"**{perso_a_placer['nom']}** a été placé dans le slot {slot} de votre réserve.")


    @equiper.command(name="pouvoir", description="Équipe un pouvoir sur un personnage de votre réserve.")
    @app_commands.autocomplete(nom_pouvoir=user_pouvoir_autocompletion)
    async def equiper_pouvoir(self, interaction: discord.Interaction, slot_personnage: int, slot_pouvoir: int, nom_pouvoir: str):
        if not (1 <= slot_personnage <= 3 and 1 <= slot_pouvoir <= 3): return await interaction.response.send_message("Erreur : Les slots doivent être entre 1 et 3.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        personnage = user_inv["reserve_combat"][slot_personnage - 1]
        if not personnage: return await interaction.response.send_message(f"Le slot de personnage {slot_personnage} est vide.", ephemeral=True)
        pouvoir_a_equiper = next((p for p in user_inv["pouvoirs"] if p["nom"].lower() == nom_pouvoir.lower()), None)
        if not pouvoir_a_equiper: return await interaction.response.send_message(f"Vous ne possédez pas '{nom_pouvoir}'.", ephemeral=True)
        if "pouvoirs" not in personnage or personnage["pouvoirs"] is None: personnage["pouvoirs"] = [None, None, None]
        personnage["pouvoirs"][slot_pouvoir - 1] = copy.deepcopy(pouvoir_a_equiper)
        self.bot.save_data()
        await interaction.response.send_message(f"Le pouvoir **{pouvoir_a_equiper['nom']}** a été équipé sur **{personnage['nom']}** (slot {slot_pouvoir}).")

    @equiper.command(name="equipement", description="Équipe un objet sur un personnage de votre réserve.")
    @app_commands.autocomplete(nom_equipement=user_equipement_autocompletion)
    async def equiper_equipement(self, interaction: discord.Interaction, slot_personnage: int, nom_equipement: str):
        if not 1 <= slot_personnage <= 3: return await interaction.response.send_message("Erreur : Le slot du personnage doit être 1, 2, ou 3.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        personnage = user_inv["reserve_combat"][slot_personnage - 1]
        if not personnage: return await interaction.response.send_message(f"Le slot de personnage {slot_personnage} est vide.", ephemeral=True)
        equipement_a_equiper = next((eq for eq in user_inv["equipements"] if eq["nom"].lower() == nom_equipement.lower()), None)
        if not equipement_a_equiper: return await interaction.response.send_message(f"Vous ne possédez pas l'équipement '{nom_equipement}'.", ephemeral=True)
        if personnage.get("equipement") is not None: return await interaction.response.send_message(f"**{personnage['nom']}** a déjà un équipement. Retirez-le d'abord.", ephemeral=True)
        personnage["equipement"] = copy.deepcopy(equipement_a_equiper)
        self.bot.save_data()
        await interaction.response.send_message(f"L'équipement **{equipement_a_equiper['nom']}** a été équipé sur **{personnage['nom']}**.")

    # --- Groupe /retirer ---
    retirer = app_commands.Group(name="retirer", description="Commandes pour retirer des objets de votre réserve.")
    
    @retirer.command(name="personnage", description="Retire un personnage de votre réserve de combat.")
    async def retirer_personnage(self, interaction: discord.Interaction, slot: int):

        game_manager_cog = self.bot.get_cog('GameManagerCog')        
        if game_manager_cog and interaction.channel.id in game_manager_cog.active_games:            
            player_state = game_manager_cog.active_games[interaction.channel.id]['players'].get(interaction.user.id)            
            if player_state:                
                if not 1 <= slot <= 3: return await interaction.response.send_message("Le slot doit être 1, 2, ou 3.", ephemeral=True)                                
                perso_a_retirer = player_state["reserve_combat"][slot - 1]                
                if perso_a_retirer is None: return await interaction.response.send_message(f"Le slot {slot} est déjà vide.", ephemeral=True)                                
                # Remettre les pouvoirs et équipements dans l'inventaire de partie                
                for p in perso_a_retirer.get("pouvoirs", []):                    
                    if p: player_state['inventory']['pouvoirs'].append(p)                
                if perso_a_retirer.get("equipement"):                    
                    player_state['inventory']['equipements'].append(perso_a_retirer["equipement"])                
                player_state["reserve_combat"][slot - 1] = None                
                await interaction.response.send_message(f"**{perso_a_retirer['nom']}** a été retiré de la réserve.", ephemeral=True)                
                await game_manager_cog._send_reserve_view_dm(player_state)                
                await game_manager_cog._send_inventories_dm(player_state)                
                return
        if not 1 <= slot <= 3: return await interaction.response.send_message("Erreur : Le slot doit être 1, 2, ou 3.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        if user_inv["reserve_combat"][slot - 1] is None: return await interaction.response.send_message(f"Le slot {slot} est déjà vide.", ephemeral=True)
        nom_perso_retire = user_inv["reserve_combat"][slot - 1]['nom']
        user_inv["reserve_combat"][slot - 1] = None
        self.bot.save_data()
        await interaction.response.send_message(f"**{nom_perso_retire}** a été retiré du slot {slot}.")

    @retirer.command(name="pouvoir", description="Retire un pouvoir d'un personnage de votre réserve.")
    async def retirer_pouvoir(self, interaction: discord.Interaction, slot_personnage: int, slot_pouvoir: int):
        if not (1 <= slot_personnage <= 3 and 1 <= slot_pouvoir <= 3): return await interaction.response.send_message("Erreur : Les slots doivent être entre 1 et 3.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        personnage = user_inv["reserve_combat"][slot_personnage - 1]
        if not personnage: return await interaction.response.send_message(f"Le slot de personnage {slot_personnage} est vide.", ephemeral=True)
        if "pouvoirs" not in personnage or personnage["pouvoirs"][slot_pouvoir - 1] is None: return await interaction.response.send_message(f"Le slot de pouvoir {slot_pouvoir} de **{personnage['nom']}** est déjà vide.", ephemeral=True)
        nom_pouvoir_retire = personnage["pouvoirs"][slot_pouvoir - 1]['nom']
        personnage["pouvoirs"][slot_pouvoir - 1] = None
        self.bot.save_data()
        await interaction.response.send_message(f"Le pouvoir **{nom_pouvoir_retire}** a été retiré de **{personnage['nom']}**.")

    @retirer.command(name="equipement", description="Retire un équipement d'un personnage de votre réserve.")
    async def retirer_equipement(self, interaction: discord.Interaction, slot_personnage: int):
        if not 1 <= slot_personnage <= 3: return await interaction.response.send_message("Erreur : Le slot doit être 1, 2, ou 3.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        personnage = user_inv["reserve_combat"][slot_personnage - 1]
        if not personnage: return await interaction.response.send_message(f"Le slot de personnage {slot_personnage} est vide.", ephemeral=True)
        if not personnage.get("equipement"): return await interaction.response.send_message(f"**{personnage['nom']}** n'a pas d'équipement.", ephemeral=True)
        nom_equip_retire = personnage["equipement"]['nom']
        personnage["equipement"] = None
        self.bot.save_data()
        await interaction.response.send_message(f"L'équipement **{nom_equip_retire}** a été retiré de **{personnage['nom']}**.")

    # --- Groupe /deplacer (un seul sous-groupe pour l'instant) ---
    deplacer = app_commands.Group(name="deplacer", description="Commandes pour réorganiser votre réserve.")
    
    @deplacer.command(name="personnage", description="Échange la position de deux personnages dans votre réserve.")
    async def deplacer_personnage(self, interaction: discord.Interaction, slot_origine: int, slot_destination: int):
        game_manager_cog = self.bot.get_cog('GameManagerCog')        
        if game_manager_cog and interaction.channel.id in game_manager_cog.active_games:            
            player_state = game_manager_cog.active_games[interaction.channel.id]['players'].get(interaction.user.id)            
            if player_state:                
                if not (1 <= slot_origine <= 3 and 1 <= slot_destination <= 3): return await interaction.response.send_message("Les slots doivent être entre 1 et 3.", ephemeral=True)                
                if slot_origine == slot_destination: return await interaction.response.send_message("Les slots sont identiques.", ephemeral=True)                                
                reserve = player_state["reserve_combat"]                
                reserve[slot_origine - 1], reserve[slot_destination - 1] = reserve[slot_destination - 1], reserve[slot_origine - 1]                
                await interaction.response.send_message(f"Les personnages des slots {slot_origine} et {slot_destination} ont été échangés.", ephemeral=True)                                
                await game_manager_cog._send_reserve_view_dm(player_state)                
                # Pas besoin de rafraîchir l'inventaire ici                
                return

        if not (1 <= slot_origine <= 3 and 1 <= slot_destination <= 3): return await interaction.response.send_message("Erreur : Les slots doivent être entre 1 et 3.", ephemeral=True)
        if slot_origine == slot_destination: return await interaction.response.send_message("Les slots sont identiques.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        reserve = user_inv["reserve_combat"]
        reserve[slot_origine - 1], reserve[slot_destination - 1] = reserve[slot_destination - 1], reserve[slot_origine - 1]
        self.bot.save_data()
        await interaction.response.send_message(f"Les contenus des slots {slot_origine} et {slot_destination} ont été échangés.")
        
        
    # Dans cogs/gestion.py, à l'intérieur de la classe GestionCog

    @app_commands.command(name="profil", description="Affiche le statut des joueurs dans la partie actuelle.")
    async def profil(self, interaction: discord.Interaction):
        game_manager_cog = self.bot.get_cog('GameManagerCog')
        if not game_manager_cog or interaction.channel.id not in game_manager_cog.active_games:
            return await interaction.response.send_message("Aucune partie n'est en cours dans ce salon.", ephemeral=True)

        game_state = game_manager_cog.active_games[interaction.channel.id]
        
        embed = discord.Embed(title="Statut de la Partie", color=discord.Color.blue())

        for player_id, player_data in game_state['players'].items():
            embed.add_field(
                name=f"👤 {player_data['member'].display_name}",
                value=f"❤️ **HP :** {player_data['hp']}\n💰 **Gold :** {player_data['gold']}",
                inline=True
            )
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ... le reste de tes commandes comme /catalogue etc.

    # --- Groupe /catalogue ---
    catalogue = app_commands.Group(name="catalogue", description="Affiche les catalogues du jeu.")

    @catalogue.command(name="personnages", description="Affiche tous les personnages disponibles dans le jeu.")
    async def catalogue_personnages(self, interaction: discord.Interaction):
        if not self.bot.catalogue_personnages: return await interaction.response.send_message("Le catalogue de personnages est vide.")
        embed = discord.Embed(title="Catalogue des Personnages", color=discord.Color.green())
        for nom, perso in self.bot.catalogue_personnages.items():
            details = (f"**Attaque :** {perso['attaque']} | **PV :** {perso['pv']}\n"f"**Capacité :** {perso['capacite_unique']}\n*{perso['description_capacite']}*")
            embed.add_field(name=f"**{perso['nom']}** (Niv. 1)", value=details, inline=False)
        await interaction.response.send_message(embed=embed)

    @catalogue.command(name="pouvoirs", description="Affiche tous les pouvoirs disponibles dans le jeu.")
    async def catalogue_pouvoirs(self, interaction: discord.Interaction):
        if not self.bot.catalogue_de_pouvoirs: return await interaction.response.send_message("Le catalogue des pouvoirs est vide.")
        embed = discord.Embed(title="Catalogue des Pouvoirs", color=discord.Color.purple())
        for nom, pouvoir in self.bot.catalogue_de_pouvoirs.items():
            details = (f"**Activation :** {pouvoir['activation'] if pouvoir['nom'] != 'Chaos' else '??'}%\n"f"*{pouvoir['description']}*")
            embed.add_field(name=f"**{pouvoir['nom']}**", value=details, inline=False)
        await interaction.response.send_message(embed=embed)

    @catalogue.command(name="equipements", description="Affiche tous les équipements disponibles dans le jeu.")
    async def catalogue_equipements(self, interaction: discord.Interaction):
        if not self.bot.catalogue_equipements: return await interaction.response.send_message("Le catalogue des équipements est vide.")
        embed = discord.Embed(title="Catalogue des Équipements", color=discord.Color.dark_gold())
        for nom, equip in self.bot.catalogue_equipements.items():
            details = f"*{equip['description']}*"
            embed.add_field(name=f"**{equip['nom']}**", value=details, inline=False)
        await interaction.response.send_message(embed=embed)

    # --- Groupe /inventaire ---
    inventaire = app_commands.Group(name="inventaire", description="Affiche vos inventaires.")

    @inventaire.command(name="personnages", description="Affiche votre inventaire de personnages.")
    async def inventaire_personnages(self, interaction: discord.Interaction):
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        if not user_inv["personnages"]: return await interaction.response.send_message("Votre inventaire de personnages est vide.", ephemeral=True)
        embed = discord.Embed(title=f"Inventaire de Personnages de {interaction.user.name}", color=discord.Color.blue())
        for perso in user_inv["personnages"]:
            stats = (f"**Niveau :** {perso.get('niveau', 1)}\n**Attaque :** {perso['attaque']} | **PV :** {perso['pv']}\n**XP :** {perso.get('xp', 0)}")
            embed.add_field(name=f"**{perso['nom']}**", value=stats, inline=False)
        await interaction.response.send_message(embed=embed)


    @inventaire.command(name="pouvoirs", description="Affiche votre inventaire de pouvoirs.")
    async def inventaire_pouvoirs(self, interaction: discord.Interaction):
        # --- DÉBUT DE LA MODIFICATION ---
        # On vérifie si le joueur est dans une partie active dans ce salon
        game_manager_cog = self.bot.get_cog('GameManagerCog')        
        if game_manager_cog and interaction.channel.id in game_manager_cog.active_games:            
            player_state = game_manager_cog.active_games[interaction.channel.id]['players'].get(interaction.user.id)            
            if player_state:                
                await interaction.response.send_message("Votre inventaire de partie vous a été envoyé en message privé.", ephemeral=True)                
                await game_manager_cog._send_inventories_dm(player_state)                
                return

        # --- FIN DE LA MODIFICATION ---
        
        # Si aucune partie n'est trouvée, on exécute le code original pour l'inventaire permanent.
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        if not user_inv.get("pouvoirs"):
            return await interaction.response.send_message("Votre inventaire de pouvoirs permanent est vide.", ephemeral=True)
        
        embed = discord.Embed(title=f"Inventaire de Pouvoirs de {interaction.user.name}", color=discord.Color.magenta())
        pouvoirs_counts = {}
        for p in user_inv["pouvoirs"]:
            pouvoirs_counts[p['nom']] = pouvoirs_counts.get(p['nom'], 0) + 1
        description = "\n".join([f"**{nom}** x{count}" for nom, count in pouvoirs_counts.items()])
        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True) # L'inventaire permanent peut rester public ou être ephemeral

    @inventaire.command(name="equipements", description="Affiche votre inventaire d'équipements.")
    async def inventaire_equipements(self, interaction: discord.Interaction):
        game_manager_cog = self.bot.get_cog('GameManagerCog')        
        if game_manager_cog and interaction.channel.id in game_manager_cog.active_games:            
            player_state = game_manager_cog.active_games[interaction.channel.id]['players'].get(interaction.user.id)            
            if player_state:                
                await interaction.response.send_message("Votre inventaire de partie vous a été envoyé en message privé.", ephemeral=True)                
                await game_manager_cog._send_inventories_dm(player_state)               
                return
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        if not user_inv["equipements"]: return await interaction.response.send_message("Votre inventaire d'équipements est vide.", ephemeral=True)
        embed = discord.Embed(title=f"Inventaire d'Équipements de {interaction.user.name}", color=discord.Color.light_grey())
        equip_counts = {}
        for eq in user_inv["equipements"]:
            equip_counts[eq['nom']] = equip_counts.get(eq['nom'], 0) + 1
        description = "\n".join([f"**{nom}** x{count}" for nom, count in equip_counts.items()])
        embed.description = description
        await interaction.response.send_message(embed=embed)
    
    # --- Commandes restantes ---
    @app_commands.command(name="menu", description="Affiche le menu d'aide avec toutes les commandes.")
    async def menu(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📜 Menu des Commandes", description="Utilisez les commandes avec `/`.", color=discord.Color.gold())
        cmd_joueur = ("**/catalogue [personnages/pouvoirs/equipements]**\n"
                      "**/inventaire [personnages/pouvoirs/equipements]**\n"
                      "**/voir_reserve**\n"
                      "**/equiper [personnage/pouvoir/equipement]**\n"
                      "**/retirer [personnage/pouvoir/equipement]**\n"
                      "**/deplacer personnage**\n"
                      "**/combat_test**, **/combat_test_aleatoire**")
        embed.add_field(name="🤖 Commandes Joueur", value=cmd_joueur, inline=False)
        if await self.bot.is_owner(interaction.user):
            cmd_admin = ("**/admin_creer [personnage/pouvoir/equipement]**\n"
                         "**/admin_modifier [personnage/pouvoir/equipement]**\n"
                         "**/admin_donner [personnage/pouvoir/equipement]**\n"
                         "**/admin_retirer [personnage/pouvoir/equipement]**\n"
                         "**/supprimer [personnage/pouvoir/equipement]**\n"
                         "**/combat_admin**")
            embed.add_field(name="👑 Commandes Admin", value=cmd_admin, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="voir_reserve", description="Affiche votre réserve de combat actuelle.")
    async def voir_reserve(self, interaction: discord.Interaction):
        game_manager_cog = self.bot.get_cog('GameManagerCog')        
        if game_manager_cog and interaction.channel.id in game_manager_cog.active_games:            
            game_state = game_manager_cog.active_games[interaction.channel.id]            
            player_state = game_state['players'].get(interaction.user.id)            
            if player_state:                
                await interaction.response.send_message("Votre réserve de partie vous a été envoyée en message privé.", ephemeral=True)                
                # On appelle notre nouvelle fonction centralisée                
                await game_manager_cog._send_reserve_view_dm(player_state)                
                return
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        reserve = user_inv["reserve_combat"]
        embed = discord.Embed(title=f"Réserve de Combat de {interaction.user.name}", color=discord.Color.orange())
        for i, perso in enumerate(reserve):
            if perso:

                pv_base = perso['pv']                                
                # On prépare une variable temporaire pour l'affichage                
                pv_a_afficher = pv_base                                
                # On vérifie si l'équipement est le Grimoire interdit                
                if perso.get("equipement") and perso["equipement"].get("nom") == "Grimoire interdit":                    
                    # On calcule la nouvelle valeur, mais SANS modifier l'objet 'perso'                    
                    pv_a_afficher = math.ceil(pv_base * 0.25)
                attaque_base = perso['attaque']                
                attaque_a_afficher = attaque_base                
                if perso.get("equipement") and perso["equipement"].get("nom") == "Hachoir":                    
                    attaque_a_afficher = attaque_base + 3
                if perso.get("equipement") and perso["equipement"].get("nom") == "Lance-bouclier":                    
                    attaque_a_afficher += 5                    
                    # Pour les PV, on se base sur les PV du catalogue, pas les PV actuels potentiellement réduits                    
                    perso_catalogue = self.bot.catalogue_personnages.get(perso['nom'], {})                    
                    pv_catalogue = perso_catalogue.get('pv', pv_base)                    
                    pv_a_afficher = pv_catalogue + 5
                details = (f"**Attaque :** {attaque_a_afficher} | **PV :** {pv_a_afficher}\n"
                           f"**Niveau :** {perso.get('niveau', 1)} | **XP :** {perso.get('xp', 0)}")
                if perso.get("equipement"): details += f"\n**Équipement :** {perso['equipement']['nom']}"
                else: details += f"\n**Équipement :** Vide"
                pouvoirs_str = ""
                for j, p in enumerate(perso.get("pouvoirs", [None, None, None])):
                    if p:
                        display_chance = ""
                        if p['nom'] == "Chaos": display_chance = "??%"
                        else:
                            activation_chance = p['activation']
                            if p['nom'] == "Pile ou Face" and perso['nom'] == "Le Parieur": activation_chance = 50
                            elif p['nom'] == "Armure" and perso['nom'] == "La Samourai": activation_chance = 50
                            elif p['nom'] == "Batteries d'urgences" and perso['nom'] == "Le Robot": activation_chance = 50
                            elif p['nom'] == "Nécromancie" and perso['nom'] == "La Nécromancienne": activation_chance = 50
                            elif p['nom'] == "Bénédiction" and perso['nom'] == "La Qilin": activation_chance = 50
                            display_chance = f"{activation_chance}%"
                        pouvoirs_str += f"\n> Slot {j+1}: {p['nom']} ({display_chance})"
                    else: pouvoirs_str += f"\n> Slot {j+1}: Vide"
                details += pouvoirs_str
                embed.add_field(name=f"Slot {i + 1} : {perso['nom']}", value=details, inline=False)
            else:
                embed.add_field(name=f"Slot {i + 1} : Vide", value="Utilisez `/equiper personnage`", inline=False)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GestionCog(bot))