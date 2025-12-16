import discord
from discord import app_commands
from discord.ext import commands
import copy

# Fonctions d'autocomplétion pour les commandes de ce Cog
async def catalogue_personnage_autocompletion(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = [nom for nom in interaction.client.catalogue_personnages.keys()]
    return [app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()][:25]

async def catalogue_pouvoir_autocompletion(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = [nom for nom in interaction.client.catalogue_de_pouvoirs.keys()]
    return [app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()][:25]

async def catalogue_equipement_autocompletion(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:        
    choices = [nom for nom in interaction.client.catalogue_equipements.keys()]        
    return [app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()][:25]

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def sync(self, ctx):
        synced = await self.bot.tree.sync()
        await ctx.send(f"Synchronisé {len(synced)} commande(s) avec Discord.")

    admin_creer = app_commands.Group(name="admin_creer", description="[ADMIN] Commandes de création.")
    @admin_creer.command(name="personnage", description="[ADMIN] Crée un nouveau personnage dans le catalogue.")
    async def admin_creer_personnage(self, interaction: discord.Interaction, nom: str, attaque: int, pv: int, capacite: str, description_capacite: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        if nom.lower() in (k.lower() for k in self.bot.catalogue_personnages.keys()): return await interaction.response.send_message(f"Erreur : **{nom}** existe déjà.", ephemeral=True)
        nouveau_personnage = {"nom": nom, "niveau": 1, "attaque": attaque, "pv": pv, "xp": 0, "capacite_unique": capacite, "description_capacite": description_capacite}
        self.bot.catalogue_personnages[nom] = nouveau_personnage
        self.bot.save_data()
        await interaction.response.send_message(f"Le personnage **{nom}** a été ajouté au catalogue !")

    @admin_creer.command(name="pouvoir", description="[ADMIN] Crée un nouveau pouvoir dans le catalogue.")
    async def admin_creer_pouvoir(self, interaction: discord.Interaction, nom: str, description: str, activation: int):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        if nom.lower() in (k.lower() for k in self.bot.catalogue_de_pouvoirs.keys()): return await interaction.response.send_message(f"Erreur : **{nom}** existe déjà.", ephemeral=True)
        nouveau_pouvoir = {"nom": nom, "description": description, "activation": activation}
        self.bot.catalogue_de_pouvoirs[nom] = nouveau_pouvoir
        self.bot.save_data()
        await interaction.response.send_message(f"Le pouvoir **{nom}** a été ajouté au catalogue !")

    admin_modifier = app_commands.Group(name="admin_modifier", description="[ADMIN] Commandes de modification.")
    @admin_modifier.command(name="personnage", description="[ADMIN] Modifie une stat d'un personnage partout dans le jeu.")
    @app_commands.autocomplete(nom_personnage=catalogue_personnage_autocompletion)
    async def admin_modifier_personnage(self, interaction: discord.Interaction, nom_personnage: str, stat: str, nouvelle_valeur: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        nom_perso_reel = next((nom for nom in self.bot.catalogue_personnages if nom.lower() == nom_personnage.lower()), None)
        if not nom_perso_reel: return await interaction.response.send_message(f"Erreur : Personnage '{nom_personnage}' introuvable.", ephemeral=True)
        perso_a_modifier = self.bot.catalogue_personnages[nom_perso_reel]
        stat = stat.lower()
        stats_valides = ["attaque", "pv", "capacite_unique", "description_capacite"]
        if stat not in stats_valides: return await interaction.response.send_message(f"Erreur : Stat invalide. Stats modifiables : `{', '.join(stats_valides)}`.", ephemeral=True)
        ancienne_valeur = perso_a_modifier.get(stat, "N/A")
        valeur_finale = int(nouvelle_valeur) if stat in ["attaque", "pv"] else nouvelle_valeur
        perso_a_modifier[stat] = valeur_finale
        for user_inv in self.bot.inventaires.values():
            for p in user_inv.get("personnages", []) + user_inv.get("reserve_combat", []):
                if p and p['nom'] == nom_perso_reel: p[stat] = valeur_finale
        self.bot.save_data()
        await interaction.response.send_message(f"**{nom_perso_reel}** a été mis à jour ! **{stat.capitalize()}** : `{ancienne_valeur}` → `{valeur_finale}`.")

    @admin_modifier.command(name="pouvoir", description="[ADMIN] Modifie une stat d'un pouvoir partout dans le jeu.")
    @app_commands.autocomplete(nom_pouvoir=catalogue_pouvoir_autocompletion)
    async def admin_modifier_pouvoir(self, interaction: discord.Interaction, nom_pouvoir: str, stat: str, nouvelle_valeur: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        nom_pouvoir_reel = next((nom for nom in self.bot.catalogue_de_pouvoirs if nom.lower() == nom_pouvoir.lower()), None)
        if not nom_pouvoir_reel: return await interaction.response.send_message(f"Erreur : Pouvoir '{nom_pouvoir}' introuvable.", ephemeral=True)
        pouvoir_a_modifier = self.bot.catalogue_de_pouvoirs[nom_pouvoir_reel]
        stat = stat.lower()
        stats_valides = ["description", "activation"]
        if stat not in stats_valides: return await interaction.response.send_message(f"Erreur : Stat invalide. Stats modifiables : `{', '.join(stats_valides)}`.", ephemeral=True)
        ancienne_valeur = pouvoir_a_modifier.get(stat, "N/A")
        valeur_finale = int(nouvelle_valeur) if stat == "activation" else nouvelle_valeur
        pouvoir_a_modifier[stat] = valeur_finale
        for user_inv in self.bot.inventaires.values():
            for p in user_inv.get("pouvoirs", []):
                if p and p['nom'] == nom_pouvoir_reel: p[stat] = valeur_finale
            for perso in user_inv.get("reserve_combat", []):
                if perso and perso.get("pouvoirs"):
                    for slot_p in perso["pouvoirs"]:
                        if slot_p and slot_p['nom'] == nom_pouvoir_reel: slot_p[stat] = valeur_finale
        self.bot.save_data()
        await interaction.response.send_message(f"**{nom_pouvoir_reel}** a été mis à jour ! **{stat.capitalize()}** : `{ancienne_valeur}` → `{valeur_finale}`.")

    admin_donner = app_commands.Group(name="admin_donner", description="[ADMIN] Commandes pour donner des objets à un joueur.")
    @admin_donner.command(name="personnage", description="[ADMIN] Donne un personnage à un joueur.")
    @app_commands.autocomplete(nom_personnage=catalogue_personnage_autocompletion)
    async def admin_donner_personnage(self, interaction: discord.Interaction, membre: discord.Member, nom_personnage: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        perso_catalogue = next((p for nom, p in self.bot.catalogue_personnages.items() if nom.lower() == nom_personnage.lower()), None)
        if not perso_catalogue: return await interaction.response.send_message(f"Personnage '{nom_personnage}' introuvable.", ephemeral=True)
        self.bot.get_user_inventory(membre.id)["personnages"].append(copy.deepcopy(perso_catalogue))
        self.bot.save_data()
        await interaction.response.send_message(f"**{perso_catalogue['nom']}** a été ajouté à l'inventaire de {membre.display_name}.")

    @admin_donner.command(name="pouvoir", description="[ADMIN] Donne un pouvoir à un joueur.")
    @app_commands.autocomplete(nom_pouvoir=catalogue_pouvoir_autocompletion)
    async def admin_donner_pouvoir(self, interaction: discord.Interaction, membre: discord.Member, nom_pouvoir: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        pouvoir_catalogue = next((p for nom, p in self.bot.catalogue_de_pouvoirs.items() if nom.lower() == nom_pouvoir.lower()), None)
        if not pouvoir_catalogue: return await interaction.response.send_message(f"Pouvoir '{nom_pouvoir}' introuvable.", ephemeral=True)
        self.bot.get_user_inventory(membre.id)["pouvoirs"].append(copy.deepcopy(pouvoir_catalogue))
        self.bot.save_data()
        await interaction.response.send_message(f"Le pouvoir **{pouvoir_catalogue['nom']}** a été ajouté à l'inventaire de {membre.display_name}.")

    admin_retirer = app_commands.Group(name="admin_retirer", description="[ADMIN] Commandes pour retirer des objets à un joueur.")
    @admin_retirer.command(name="personnage", description="[ADMIN] Retire un personnage de l'inventaire d'un joueur.")
    @app_commands.autocomplete(nom_personnage=catalogue_personnage_autocompletion)
    async def admin_retirer_personnage(self, interaction: discord.Interaction, membre: discord.Member, nom_personnage: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(membre.id)
        perso_a_retirer = next((p for p in user_inv["personnages"] if p["nom"].lower() == nom_personnage.lower()), None)
        if not perso_a_retirer: return await interaction.response.send_message(f"{membre.display_name} ne possède pas '{nom_personnage}'.", ephemeral=True)
        user_inv["personnages"].remove(perso_a_retirer)
        msg = f"**{perso_a_retirer['nom']}** a été retiré de l'inventaire de {membre.display_name}."
        for i, p in enumerate(user_inv["reserve_combat"]):
            if p and p["nom"] == perso_a_retirer["nom"]:
                user_inv["reserve_combat"][i] = None
                msg += "\nIl a aussi été retiré de sa réserve."
        self.bot.save_data()
        await interaction.response.send_message(msg)

    @admin_retirer.command(name="pouvoir", description="[ADMIN] Retire un pouvoir de l'inventaire d'un joueur.")
    @app_commands.autocomplete(nom_pouvoir=catalogue_pouvoir_autocompletion)
    async def admin_retirer_pouvoir(self, interaction: discord.Interaction, membre: discord.Member, nom_pouvoir: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(membre.id)
        pouvoir_a_retirer = next((p for p in user_inv["pouvoirs"] if p["nom"].lower() == nom_pouvoir.lower()), None)
        if not pouvoir_a_retirer: return await interaction.response.send_message(f"{membre.display_name} ne possède pas '{nom_pouvoir}'.", ephemeral=True)
        user_inv["pouvoirs"].remove(pouvoir_a_retirer)
        msg = f"Le pouvoir **{pouvoir_a_retirer['nom']}** a été retiré de l'inventaire de {membre.display_name}."
        for perso in user_inv["reserve_combat"]:
            if perso and perso.get("pouvoirs"):
                for i, p in enumerate(perso["pouvoirs"]):
                    if p and p["nom"] == pouvoir_a_retirer["nom"]:
                        perso["pouvoirs"][i] = None
        self.bot.save_data()
        await interaction.response.send_message(msg)

    @app_commands.command(name="supprimer_personnage", description="[ADMIN] Supprime un personnage du jeu (catalogue et inventaires).")
    @app_commands.autocomplete(nom_personnage=catalogue_personnage_autocompletion)
    async def supprimer_personnage(self, interaction: discord.Interaction, nom_personnage: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        nom_perso_reel = next((nom for nom in self.bot.catalogue_personnages if nom.lower() == nom_personnage.lower()), None)
        if not nom_perso_reel: return await interaction.response.send_message(f"Erreur : Personnage '{nom_personnage}' introuvable.", ephemeral=True)
        del self.bot.catalogue_personnages[nom_perso_reel]
        count = 0
        for user_inv in self.bot.inventaires.values():
            initial_len = len(user_inv["personnages"])
            user_inv["personnages"] = [p for p in user_inv["personnages"] if p['nom'] != nom_perso_reel]
            count += initial_len - len(user_inv["personnages"])
            for i, p in enumerate(user_inv["reserve_combat"]):
                if p and p['nom'] == nom_perso_reel:
                    user_inv["reserve_combat"][i] = None
        self.bot.save_data()
        await interaction.response.send_message(f"**{nom_perso_reel}** a été supprimé du catalogue et retiré de **{count}** inventaires.")

    @app_commands.command(name="supprimer_pouvoir", description="[ADMIN] Supprime un pouvoir du jeu (catalogue et inventaires).")
    @app_commands.autocomplete(nom_pouvoir=catalogue_pouvoir_autocompletion)
    async def supprimer_pouvoir(self, interaction: discord.Interaction, nom_pouvoir: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        nom_pouvoir_reel = next((nom for nom in self.bot.catalogue_de_pouvoirs if nom.lower() == nom_pouvoir.lower()), None)
        if not nom_pouvoir_reel: return await interaction.response.send_message(f"Erreur : Pouvoir '{nom_pouvoir}' introuvable.", ephemeral=True)
        del self.bot.catalogue_de_pouvoirs[nom_pouvoir_reel]
        for user_inv in self.bot.inventaires.values():
            user_inv["pouvoirs"] = [p for p in user_inv.get("pouvoirs", []) if p['nom'] != nom_pouvoir_reel]
            for perso in user_inv.get("reserve_combat", []):
                if perso and perso.get("pouvoirs"):
                    for i, p_slot in enumerate(perso["pouvoirs"]):
                        if p_slot and p_slot['nom'] == nom_pouvoir_reel:
                            perso["pouvoirs"][i] = None
        self.bot.save_data()
        await interaction.response.send_message(f"Le pouvoir **{nom_pouvoir_reel}** a été définitivement supprimé du jeu.")
    
        # Dans la classe AdminCog

    # --- Commande /admin_creer equipement ---
    @admin_creer.command(name="equipement", description="[ADMIN] Crée un nouvel équipement dans le catalogue.")
    async def admin_creer_equipement(self, interaction: discord.Interaction, nom: str, description: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        if nom.lower() in (k.lower() for k in self.bot.catalogue_equipements.keys()): return await interaction.response.send_message(f"Erreur : **{nom}** existe déjà.", ephemeral=True)
        
        # Pour l'instant, on stocke l'effet en texte, on le rendra fonctionnel plus tard
        nouveau_equipement = {"nom": nom, "description": description, "effet": "Aucun effet défini"}
        self.bot.catalogue_equipements[nom] = nouveau_equipement
        self.bot.save_data()
        await interaction.response.send_message(f"L'équipement **{nom}** a été ajouté au catalogue !")

    # --- Commande /admin_donner equipement ---
    @admin_donner.command(name="equipement", description="[ADMIN] Donne un équipement à un joueur.")
    @app_commands.autocomplete(nom_equipement=catalogue_equipement_autocompletion)
    async def admin_donner_equipement(self, interaction: discord.Interaction, membre: discord.Member, nom_equipement: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        equipement_catalogue = next((eq for nom, eq in self.bot.catalogue_equipements.items() if nom.lower() == nom_equipement.lower()), None)
        if not equipement_catalogue: return await interaction.response.send_message(f"Équipement '{nom_equipement}' introuvable.", ephemeral=True)
        self.bot.get_user_inventory(membre.id)["equipements"].append(copy.deepcopy(equipement_catalogue))
        self.bot.save_data()
        await interaction.response.send_message(f"L'équipement **{equipement_catalogue['nom']}** a été ajouté à l'inventaire de {membre.display_name}.")

    # --- Commande /admin_retirer equipement ---
    @admin_retirer.command(name="equipement", description="[ADMIN] Retire un équipement de l'inventaire d'un joueur.")
    @app_commands.autocomplete(nom_equipement=catalogue_equipement_autocompletion)
    async def admin_retirer_equipement(self, interaction: discord.Interaction, membre: discord.Member, nom_equipement: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        user_inv = self.bot.get_user_inventory(membre.id)
        equipement_a_retirer = next((eq for eq in user_inv["equipements"] if eq["nom"].lower() == nom_equipement.lower()), None)
        if not equipement_a_retirer: return await interaction.response.send_message(f"{membre.display_name} ne possède pas '{nom_equipement}'.", ephemeral=True)
        
        user_inv["equipements"].remove(equipement_a_retirer)
        msg = f"L'équipement **{equipement_a_retirer['nom']}** a été retiré de l'inventaire de {membre.display_name}."
        
        # Vérifier et déséquiper des personnages dans la réserve
        for perso in user_inv["reserve_combat"]:
            if perso and perso.get("equipement") and perso["equipement"]["nom"] == equipement_a_retirer["nom"]:
                perso["equipement"] = None
                msg += f"\nIl a aussi été déséquipé de **{perso['nom']}**."

        self.bot.save_data()
        await interaction.response.send_message(msg)

    # --- Commande /supprimer_equipement --- (C'est une commande racine, pas dans un groupe)
    @app_commands.command(name="supprimer_equipement", description="[ADMIN] Supprime un équipement du jeu (catalogue et inventaires).")
    @app_commands.autocomplete(nom_equipement=catalogue_equipement_autocompletion)
    async def supprimer_equipement(self, interaction: discord.Interaction, nom_equipement: str):
        if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        nom_equip_reel = next((nom for nom in self.bot.catalogue_equipements if nom.lower() == nom_equipement.lower()), None)
        if not nom_equip_reel: return await interaction.response.send_message(f"Erreur : Équipement '{nom_equipement}' introuvable.", ephemeral=True)
        
        del self.bot.catalogue_equipements[nom_equip_reel]
        
        for user_inv in self.bot.inventaires.values():
            user_inv["equipements"] = [eq for eq in user_inv.get("equipements", []) if eq['nom'] != nom_equip_reel]
            for perso in user_inv.get("reserve_combat", []):
                if perso and perso.get("equipement") and perso["equipement"]['nom'] == nom_equip_reel:
                    perso["equipement"] = None
        
        self.bot.save_data()
        await interaction.response.send_message(f"L'équipement **{nom_equip_reel}** a été définitivement supprimé du jeu.")
    
async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))