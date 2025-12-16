import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import random
import copy
from .combat_engine_1v1 import CombatEngine
# Après les autres imports
from .ai_trainer import AITrainer
# =====================================================================================
# SECTION 1 : LES VUES DISCORD (INTERFACES GRAPHIQUES)
# =====================================================================================
# cogs/game_1v1_manager.py

# --- Vue pour le bouton Prêt ---
# --- Vue pour la Sélection de Passifs ---
class PassiveSelectionView(discord.ui.View):
    def __init__(self, available_passives):
        super().__init__(timeout=180)  # 3 minutes pour choisir
        self.chosen_passive = None
        self.available_passives = available_passives
        
        # Créer un bouton pour chaque passif disponible
        for passive_id, passive_info in available_passives.items():
            button = discord.ui.Button(
                label=passive_info['name'],
                custom_id=f"passive_{passive_id}",
                style=discord.ButtonStyle.primary
            )
            button.callback = self.passive_callback
            self.add_item(button)
    
    async def passive_callback(self, interaction: discord.Interaction):
        custom_id = interaction.data['custom_id']
        # Extraire l'ID du passif en supprimant seulement le préfixe "passive_"
        passive_id = custom_id[len("passive_"):]
        self.chosen_passive = passive_id
        
        passive_name = self.available_passives[passive_id]['name']
            
        # Désactiver les boutons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Vous avez choisi le passif **{passive_name}**!", view=self)
        self.stop()
        
class ReadyView(discord.ui.View):
    def __init__(self, manager_cog, game_state):
        super().__init__(timeout=300)
        self.manager_cog = manager_cog
        self.game_state = game_state

    @discord.ui.button(label="Prêt pour le Combat !", style=discord.ButtonStyle.success, custom_id="ready_button")
    async def ready_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player_id = interaction.user.id
        
        if player_id not in self.game_state['players']:
            return await interaction.response.send_message("Vous ne participez pas à cette partie.", ephemeral=True)

        player_state = self.game_state['players'][player_id]
        
        if player_state['is_ready']:
            return await interaction.response.send_message("Vous êtes déjà prêt.", ephemeral=True)

        player_state['is_ready'] = True
        await interaction.response.send_message(f"**{interaction.user.display_name}** est prêt !", ephemeral=False)

        opponent_state = None
        for pid, p_state in self.game_state['players'].items():
            if pid != player_id:
                opponent_state = p_state
                    
        show_opponent = self.game_state['phase'] == 'combat'
        await self.manager_cog.update_player_dashboard(player_state, opponent_state, self.game_state, locked=True, show_opponent=show_opponent)
# --- Vue pour la Roulette d'Invocation ---
class InvocationView(discord.ui.View):
    # Dans la classe InvocationView, juste après la ligne super().__init__(timeout=300)
    def __init__(self, manager_cog, player_state):
        super().__init__(timeout=300) # 5 minutes pour choisir
        self.manager_cog = manager_cog
        self.player_state = player_state
        self.chosen_char_name = None

        # Dictionnaire des descriptions courtes pour chaque personnage
        self.char_descriptions = {
            "Monstre foyer": "Tank soigneur (10 PV, 2 ATQ) - Soigne tous les alliés à 100% PV",
            "Mage des nuages": "Support (6 PV, 4 ATQ) - Rend un allié intouchable",
            "Chasseuse de prime": "Attaquant (5 PV, 4 ATQ) - Marque un ennemi pour gagner 2 PR à sa mort",
            "Oncle ben": "DPS (4 PV, 7 ATQ) - Peut inverser ses PV et ATQ",
            "Renarde": "Attaquant (8 PV, 4 ATQ) - Double dégâts + priorité d'attaque",
            "Maitre de l'arêne": "Équilibré (7 PV, 7 ATQ) - Peut récupérer 3 PV",
            "Robot radio": "Support (5 PV, 1 ATQ) - Augmente l'ATQ de tous les alliés",
            "Pyromane": "Nuke (5 PV, 5 ATQ) - Inflige 15 dégâts directs à l'adversaire",
            "Paresseuse": "Tank temporaire (3 PV, 3 ATQ) - Invulnérable puis disparaît",
            "Chevalier coton": "Tank (6 PV, 2 ATQ) - Réduit tous les dégâts à 1",
            "Artiste": "Polyvalent (6 PV, 3 ATQ) - Attaque bonus OU soins par dégâts",
            "Cape guerrière": "Support (4 PV, 4 ATQ) - Fusionne avec un allié pour le renforcer",
            "Garçon parapluie": "Économie (1 PV, 1 ATQ) - Convertit les dégâts en PR",
            "Sumo Cyborg": "Contre (4 PV, 4 ATQ) - Renvoie tous les dégâts à l'attaquant",
            "Sapin de Noël": "Debuff (2 PV, 5 ATQ) - Bloque la capacité de l'adversaire",
            "Fourmi chimère": "Évolutif (2 PV, 2 ATQ) - Invoque une fourmi plus forte",
            "Petit fantôme": "Piège (3 PV, 1 ATQ) - Réduit l'ATQ de son tueur à 1",
            "Cheffe néophyte": "Attaquant protégé (3 PV, 5 ATQ) - Recrute des gardes du corps",
            "Tempête": "Contrôle (4 PV, 4 ATQ) - Remplace l'adversaire par un plus faible",
            "Gros bourdon": "Économie (6 PV, 5 ATQ) - Vole 3 PR à l'adversaire",
            "Potion vivante": "Soin (1 PV, 1 ATQ) - Convertit tous vos PR en HP (x2)",
            "Mini Hercule": "DPS évolutif (1 PV, 1 ATQ) - Peut gagner +3 en ATQ",
            "Moine": "Économie (4 PV, 4 ATQ) - Gagne 5 PR et devient prêt au combat",
            "Couple": "Dédoublement (7 PV, 4 ATQ) - Se divise en 2 combattants de 5/5",
            "Dame champis": "Poison (5 PV, 2 ATQ) - Empoisonne tous les personnages adverses",
            "Vieux croulant": "Contrôle (4 PV, 1 ATQ) - Annule toutes les attaques pour un tour",
            "Programme": "Tech (5 PV, 5 ATQ) - Supprime un personnage de l'inventaire adverse au prochain tour.",
            "Autel vivant": "Méga tank (20 PV, 1 ATQ) - Guérit les statuts négatifs",
            "Petit bourdon": "Attaque directe (1 PV, 3 ATQ) - Attaque directement les HP adverses",
            "Fouine": "Voleur (1 PV, 1 ATQ) - Échange sa place avec le personnage adverse"
        }

        # Logique de sélection des 3 personnages
        player_pr = self.player_state['pr']
        # 1. Filtrer les personnages que le joueur peut s'offrir
        available_chars = [char for char in self.manager_cog.bot.catalogue_personnages_1v1.values() if char['cout'] <= player_pr]
        
        # 2. Grouper par coût pour assurer des coûts différents
        chars_by_cost = {}
        for char in available_chars:
            cost = char['cout']
            if cost not in chars_by_cost:
                chars_by_cost[cost] = []
            chars_by_cost[cost].append(char)

        # 3. Sélectionner 3 coûts différents (si possible)
        possible_costs = list(chars_by_cost.keys())
        num_choices = min(3, len(possible_costs))
        chosen_costs = random.sample(possible_costs, num_choices)
        
        # 4. Créer les boutons de choix
        for cost in chosen_costs:
            # Choisir un personnage au hasard pour ce coût
            char_to_offer = random.choice(chars_by_cost[cost])
            description = self.char_descriptions.get(char_to_offer['nom'], f"{char_to_offer['pv']} PV, {char_to_offer['attaque']} ATQ")
            button = discord.ui.Button(
                label=f"{char_to_offer['nom']} ({char_to_offer['cout']} PR)",
                custom_id=f"invoke_{char_to_offer['nom']}",
                style=discord.ButtonStyle.secondary
            )
            button.callback = self.invoke_callback
            self.add_item(button)

    async def invoke_callback(self, interaction: discord.Interaction):
        char_name = interaction.data['custom_id'].split('_')[1]
        self.chosen_char_name = char_name
        self.stop() # Arrête la vue
        # On désactive les boutons pour montrer que le choix a été fait
        for item in self.children:
            item.disabled = True
        description = self.char_descriptions.get(char_name, "")    
        await interaction.response.edit_message(content=f"Vous avez choisi d'invoquer **{char_name}**.\n*{description}*", view=self)
        
        
        
# ... (après la classe InvocationView) ...

# --- Vue pour la Sélection de Cible ---
class TargetSelectionView(discord.ui.View):
    def __init__(self, player_state, user_char_slot):
        super().__init__(timeout=180)
        self.chosen_target_id = None # Sera "terrain" ou un index d'inventaire (0, 1, 2)

        options = []
        # Option 1: Le personnage sur le terrain
        if player_state['terrain']:
            terrain_char = player_state['terrain']
            # On ne peut pas se cibler soi-même si la capacité est lancée depuis le terrain
            if user_char_slot != "terrain":
                 options.append(discord.SelectOption(label=f"Terrain : {terrain_char['nom']}", value="terrain"))

        # Option 2: Les personnages dans l'inventaire
        for i, inv_char in enumerate(player_state['inventaire']):
            if inv_char:
                # On ne peut pas se cibler soi-même
                if i != user_char_slot:
                    options.append(discord.SelectOption(label=f"Inventaire {i+1} : {inv_char['nom']}", value=str(i)))

        # Créer le menu déroulant seulement s'il y a des cibles valides
        if options:
            select = discord.ui.Select(placeholder="Choisissez un allié à cibler...", options=options)
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        self.chosen_target_id = interaction.data['values'][0]
        self.stop()
        # On désactive le menu pour montrer que le choix est fait
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Cible sélectionnée !", view=self)
        

# --- NOUVELLE VUE : Choix de l'Artiste ---
class ArtisteChoiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180) # 3 minutes pour choisir
        self.choice = None # Sera "abstrait" ou "contemporain"

    @discord.ui.button(label="Art abstrait (Attaque sup.)", style=discord.ButtonStyle.primary, custom_id="art_abstrait")
    async def abstrait_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.choice = "abstrait"
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Vous avez choisi l'**Art abstrait** !", view=self)
        self.stop()

    @discord.ui.button(label="Art contemporain (Soin)", style=discord.ButtonStyle.secondary, custom_id="art_contemporain")
    async def contemporain_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.choice = "contemporain"
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Vous avez choisi l'**Art contemporain** !", view=self)
        self.stop()

    

class EmpruntView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.montant_emprunte = None

        options = [discord.SelectOption(label=f"{i} PR", value=str(i)) for i in range(1, 11)]
            
        select = discord.ui.Select(placeholder="Choisissez combien de PR emprunter...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        self.montant_emprunte = int(interaction.data['values'][0])
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Vous avez choisi d'emprunter **{self.montant_emprunte} PR**.", view=self)
        self.stop()


# --- VUE TEST : Sélection de personnage du catalogue (TEMPORAIRE) ---
class TestCharacterSelectionView(discord.ui.View):
    def __init__(self, manager_cog):
        super().__init__(timeout=180)
        self.manager_cog = manager_cog
        self.chosen_char_name = None
        
        # ✅ VÉRIFIER D'ABORD SI LE CATALOGUE EXISTE ET N'EST PAS VIDE
        if not hasattr(manager_cog.bot, 'catalogue_personnages_1v1'):
            print("[ERROR] catalogue_personnages_1v1 n'existe pas!")
            return
        
        catalogue = manager_cog.bot.catalogue_personnages_1v1
        if not catalogue:
            print("[ERROR] catalogue_personnages_1v1 est VIDE!")
            return
        
        print(f"[DEBUG] Catalogue contient {len(catalogue)} personnages")
        
        # Créer un Select dropdown avec tous les personnages
        
        for page, start_idx in enumerate([0, 25]):    
            page_chars = list(catalogue.items())[start_idx:start_idx+25]    
            if not page_chars:        
                break
        
            options = []
            for char_name, char_data in page_chars:        
                options.append(discord.SelectOption(            
                                                    label=f"{char_name}",            
                                                    value=char_name        ))
            
            
            # Créer le select
            select = discord.ui.Select(
                placeholder=f"Page {page+1}...",
                options=options,
                custom_id=f"test_char_select_page_{page}"
            )
            select.callback = self.select_callback
            self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        self.chosen_char_name = interaction.data['values'][0]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Test - Personnage sélectionné: **{self.chosen_char_name}**",
            view=self
        )
        self.stop()
        
# --- Vue Principale de Gestion (Inventaire & Terrain) ---
class PlayerDashboardView(discord.ui.View):
    def __init__(self, manager_cog, player_state, game_state):
        super().__init__(timeout=None)
        self.manager_cog = manager_cog
        self.player_state = player_state
        self.game_state = game_state
        
        # --- Ligne 1 : Le Terrain ---
        terrain_char = self.player_state['terrain']
        if terrain_char:
            # Si un personnage est sur le terrain
            # Note : Pour l'instant, pas de bouton "Utiliser Capacité" sur le terrain, on simplifie.
            # On pourrait l'ajouter ici avec `row=0`
            self.add_item(discord.ui.Button(label="Renvoyer à l'inventaire", custom_id="terrain_to_inv", style=discord.ButtonStyle.secondary, row=0))
            
            has_malédiction = "statuts" in terrain_char and "Malédiction" in terrain_char["statuts"]            
            if "capacite" in terrain_char and not has_malédiction:                
                # Calculer le coût affiché en tenant compte du passif "Promotion"                
                displayed_cost = terrain_char['capacite']['cout']                
                if 'promotion' in self.player_state.get('passives', {}):                    
                    invocation_cost = terrain_char.get('cout', 0)                    
                    if invocation_cost in [6, 7, 8]:                        
                        displayed_cost = 1                               
                        # On utilise un custom_id spécial "terrain"                
                self.add_item(discord.ui.Button(label=f"Capacité ({displayed_cost} PR)", custom_id="use_ability_terrain", style=discord.ButtonStyle.success, row=0))
    
        if 'pret' in self.player_state['passives'] and not self.player_state.get('a_emprunte_ce_tour', False):                
            self.add_item(discord.ui.Button(label="Emprunter", custom_id="emprunter_pr", style=discord.ButtonStyle.danger, row=0))
            
        
        # --- Lignes 2, 3, 4 : L'Inventaire ---
        
        for i in range(3):
            inv_char = self.player_state['inventaire'][i]
            if inv_char:
                # Si un personnage est dans ce slot d'inventaire
                self.add_item(discord.ui.Button(label=f"Placer {inv_char['nom']} sur le terrain", custom_id=f"inv_to_terrain_{i}", style=discord.ButtonStyle.primary, row=i+1))
                # On ajoute le bouton pour la capacité s'il en a une
                has_malédiction = "statuts" in inv_char and "Malédiction" in inv_char["statuts"]
                if "capacite" in inv_char and not has_malédiction:
                    # Calculer le coût affiché en tenant compte du passif "Promotion"                
                    displayed_cost = inv_char['capacite']['cout']                
                    if 'promotion' in self.player_state.get('passives', {}):                    
                        # Vérifier si le coût d'invocation du personnage est 6, 7 ou 8                    
                        invocation_cost = inv_char.get('cout', 0)                    
                        if invocation_cost in [6, 7, 8]:                        
                            displayed_cost = 1
                    self.add_item(discord.ui.Button(label=f"Capacité ({displayed_cost} PR)", custom_id=f"use_ability_{i}", style=discord.ButtonStyle.success, row=i+1))
            else:
                # Si le slot est vide, bouton d'invocation
                self.add_item(discord.ui.Button(label="Invocation", custom_id=f"invocation_{i}", style=discord.ButtonStyle.secondary, row=i+1))
                
    async def _delete_message_after(self, message, seconds):
        """Supprime un message après un délai spécifié en secondes."""
        await asyncio.sleep(seconds)
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass  # Le message n'existe plus ou nous n'avons pas la permission de le supprimer
        
    def _is_attack_blocked_by_enchantment(self, char):
        """
        Vérifie si un personnage est Envoûté (ce qui bloque l'augmentation d'attaque).
        Retourne True si Envoûté, False sinon.
        """
        if char and "statuts" in char and "Envoûté" in char.get("statuts", []):
            return True
        return False

    async def interaction_check(self, interaction: discord.Interaction):
        # On attache tous les callbacks à cette seule méthode pour une gestion centralisée
        custom_id = interaction.data['custom_id']
        print(f"[DEBUG] interaction_check reçu : {custom_id}")  # ← Toujours le premier log!
        
        

        if custom_id.startswith("invocation_"):
            await self.invocation_callback(interaction)
        elif custom_id.startswith("inv_to_terrain_"):
            await self.inv_to_terrain_callback(interaction)
        elif custom_id == "terrain_to_inv":
            await self.terrain_to_inv_callback(interaction)
        elif custom_id.startswith("use_ability_"):
            await self.use_ability_callback(interaction)
        elif custom_id == "emprunter_pr":            
            await self.emprunter_callback(interaction)         
        else:        
            return False  # Seulement si RIEN ne match

            
        return True # Empêche l'interaction de continuer et évite un "Interaction a échoué"
    
    async def emprunter_callback(self, interaction: discord.Interaction):        
        view = EmpruntView()        
        await interaction.response.send_message("Combien de PR souhaitez-vous emprunter ?", view=view, ephemeral=True)        
        await view.wait()        
        if view.montant_emprunte is not None:            
            montant = view.montant_emprunte                        
            # Mettre à jour les stats du joueur            
            self.player_state['pr'] += montant            
            self.player_state['dette'] -= montant            
            self.player_state['a_emprunte_ce_tour'] = True                        
            # Mettre à jour les dashboards            
            await self.manager_cog.update_all_dashboards(self.game_state)
    

    async def invocation_callback(self, interaction: discord.Interaction):
        slot_index = int(interaction.data['custom_id'].split('_')[1])
        
        # Vérifier si le joueur a assez de PR pour invoquer le personnage le moins cher
        min_cost = min(char['cout'] for char in self.manager_cog.bot.catalogue_personnages_1v1.values())
        if self.player_state['pr'] < min_cost:
            return await interaction.response.send_message("Vous n'avez pas assez de PR pour invoquer le moindre personnage.", ephemeral=True)

        view = InvocationView(self.manager_cog, self.player_state)
        
        descriptions = []    
        for item in view.children:        
            if isinstance(item, discord.ui.Button) and item.custom_id.startswith("invoke_"):            
                char_name = item.custom_id.split('_')[1]            
                desc = view.char_descriptions.get(char_name, "")            
                descriptions.append(f"**{char_name}**: {desc}")        
        description_text = "\n".join(descriptions)    
        message = f"Choisissez un personnage à invoquer :\n\n{description_text}"
        await interaction.response.send_message(message, view=view, ephemeral=True)
        await view.wait() # On attend que le joueur choisisse

        if view.chosen_char_name:
            char_data = copy.deepcopy(self.manager_cog.bot.catalogue_personnages_1v1[view.chosen_char_name])
            if 'pv_max' not in char_data:                
                char_data['pv_max'] = char_data['pv']
                
            # Appliquer le passif "À main nue" si le joueur le possède            
            if 'a_main_nue' in self.player_state.get('passives', {}):                
                char_data['pv'] += 5                
                char_data['pv_max'] += 5                
                if "statuts" not in char_data:                    
                    char_data["statuts"] = []                
                    char_data["statuts"].append("À main nue")
                
            if self.game_state['tour'] > 1:            
                if "statuts" not in char_data:                
                    char_data["statuts"] = []            
                char_data["statuts"].append("Fatigue d'invocation")
            # Payer le coût et placer dans l'inventaire
            self.player_state['pr'] -= char_data['cout']
            self.player_state['inventaire'][slot_index] = char_data
            
            # Mettre à jour les dashboards des deux joueurs
            await self.manager_cog.update_all_dashboards(self.game_state)

    async def inv_to_terrain_callback(self, interaction: discord.Interaction):
        slot_index = int(interaction.data['custom_id'].split('_')[-1])
        char = self.player_state['inventaire'][slot_index]
        
        if "statuts" in char and "Fatigue d'invocation" in char["statuts"]:        
            return await interaction.response.send_message("Ce personnage vient d'être invoqué et est trop fatigué pour combattre ce tour-ci.", ephemeral=True)
        if self.player_state['terrain']:
            # On inverse les personnages
            self.player_state['inventaire'][slot_index], self.player_state['terrain'] = self.player_state['terrain'], self.player_state['inventaire'][slot_index]
        else:
            # Sinon, on déplace simplement
            self.player_state['terrain'] = self.player_state['inventaire'][slot_index]
            self.player_state['inventaire'][slot_index] = None
        
        self.player_state['has_placed_character'] = True
        await interaction.response.defer() # Accusé de réception
        await self.manager_cog.update_all_dashboards(self.game_state)
        
    async def terrain_to_inv_callback(self, interaction: discord.Interaction):
        # Chercher un slot vide dans l'inventaire
        try:
            empty_slot = self.player_state['inventaire'].index(None)
            self.player_state['inventaire'][empty_slot] = self.player_state['terrain']
            self.player_state['terrain'] = None
            self.player_state['has_placed_character'] = False
            await interaction.response.defer()
            await self.manager_cog.update_all_dashboards(self.game_state)
        except ValueError:
            # Si .index(None) échoue, c'est que l'inventaire est plein
            await interaction.response.send_message("Votre inventaire est plein, impossible de renvoyer le personnage.", ephemeral=True)
            
   # Dans la classe PlayerDashboardView

        # REMPLACEZ VOTRE MÉTHODE EXISTANTE PAR CELLE-CI
    async def use_ability_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        custom_id_part = interaction.data['custom_id'].split('_')[-1]
        if custom_id_part == "terrain":            
            char = self.player_state['terrain']            
            # On garde une trace de l'origine pour les capacités qui ne peuvent pas se cibler elles-mêmes            
            slot_index = "terrain"         
        else:            
            slot_index = int(custom_id_part)            
            char = self.player_state['inventaire'][slot_index]        
        if not char: # Sécurité au cas où le personnage n'existe pas            
            return await interaction.followup.send("Erreur : personnage non trouvé.", ephemeral=True)
        capacite = char['capacite']
        # Gérer le passif "À main nue" AVANT de payer le coût        
        if "À main nue" in char.get("statuts", []):            
            char["statuts"].remove("À main nue")            
            char['pv_max'] -= 5            
            # S'assure que les PV actuels ne dépassent pas les nouveaux PV max            
            char['pv'] = min(char['pv'], char['pv_max'])                        
            # Informer le joueur (optionnel mais recommandé)            
            await interaction.followup.send("👊 Le bonus de PV de votre personnage a été retiré suite à l'utilisation de sa capacité.", ephemeral=True)            
        # Marquer qu'un message a déjà été envoyé pour que les prochains soient des followups            
            passif_message_sent = True         
        else:            
            passif_message_sent = False

        # --- NOUVELLE LOGIQUE CENTRALISÉE POUR LE COÛT ET LE PASSIF ---
        actual_cost = capacite['cout']
        if 'promotion' in self.player_state.get('passives', {}):            
            invocation_cost = char.get('cout', 0)            
            if invocation_cost in [6, 7, 8]:                
                actual_cost = 1
        is_free_cast = False
        
        # Vérifier si le joueur a le passif et si la capacité est gratuite
        if ('passives' in self.player_state and 'maitre_capacites' in self.player_state['passives'] and
            self.player_state.get('ability_usage_counter', 0) == 2):
            actual_cost = 0
            is_free_cast = True

        # Vérifier si le joueur a assez de PR
        if self.player_state['pr'] < actual_cost:
            return await interaction.followup.send("Pas assez de PR pour utiliser cette capacité.", ephemeral=True)

        # Payer le coût (qui peut être 0)
        self.player_state['pr'] -= actual_cost

        # Mettre à jour le compteur et envoyer le message du passif
        if 'passives' in self.player_state and 'maitre_capacites' in self.player_state['passives']:
            if is_free_cast:
                self.player_state['ability_usage_counter'] = 0
                await interaction.followup.send("🧙 Votre passif **Maître des capacités** s'active ! Cette capacité est gratuite !", ephemeral=True)
                passif_message_sent = True
            else:
                self.player_state['ability_usage_counter'] += 1
                count = self.player_state['ability_usage_counter']
                next_ability_msg = "La prochaine sera gratuite !" if count == 2 else ""
                await interaction.followup.send(f"Utilisation de capacité {count}/2. {next_ability_msg}", ephemeral=True)
                passif_message_sent = True

        # --- FIN DE LA LOGIQUE CENTRALISÉE ---

        # Fonction utilitaire pour envoyer une réponse ou un suivi
        async def respond(message, view=None, ephemeral=True):
            if view is not None:        
                await interaction.followup.send(message, view=view, ephemeral=ephemeral)    
            else:        
                await interaction.followup.send(message, ephemeral=ephemeral)

        # --- LOGIQUE SPÉCIFIQUE À CHAQUE CAPACITÉ ---

        try:
            if capacite['nom'] == "Doux foyer":
                if self.player_state['terrain']:
                    self.player_state['terrain']['pv'] = self.player_state['terrain']['pv_max']
                for i, ally in enumerate(self.player_state['inventaire']):
                    if ally and i != slot_index:
                        ally['pv'] = ally['pv_max']
                await respond(f"La capacité **{capacite['nom']}** a été utilisée !")

            elif capacite['nom'] == "Dans les nuages":
                target_view = TargetSelectionView(self.player_state, user_char_slot=slot_index)
                if not target_view.children:
                    self.player_state['pr'] += actual_cost
                    return await respond("Il n'y a aucune autre allié à cibler.")
                await respond("Qui voulez-vous faire flotter ?", view=target_view)
                await target_view.wait()
                if target_view.chosen_target_id is not None:
                    target_id = target_view.chosen_target_id
                    target_char = self.player_state['terrain'] if target_id == "terrain" else self.player_state['inventaire'][int(target_id)]
                    if "statuts" not in target_char: target_char["statuts"] = []
                    target_char["statuts"].append("Flotte")
                else:
                    self.player_state['pr'] += actual_cost

            elif capacite['nom'] == "Cible":
                if "statuts" not in char: char["statuts"] = []
                if "En chasse" not in char["statuts"]: char["statuts"].append("En chasse")
                await respond(f"Votre **{char['nom']}** se met en chasse !")

            elif capacite['nom'] == "Bipolaire":
                if self._is_attack_blocked_by_enchantment(char):                    
                    await respond(f"👻 **{char['nom']}** est Envoûté ! L'inversion de stats est bloquée !")                
                else:
                    char['pv'], char['attaque'] = char['attaque'], char['pv']
                    if char['pv_max'] < char['pv']: char['pv_max'] = char['pv']
                    await respond(f"**{char['nom']}** a interverti ses stats !")

            elif capacite['nom'] == "Attaque surprise":
                if "statuts" not in char: char["statuts"] = []
                if "À l'affût" not in char["statuts"]: char["statuts"].append("À l'affût")
                await respond(f"**{char['nom']}** se prépare pour une attaque surprise !")

            elif capacite['nom'] == "Repos du héros":
                char['pv'] = min(char['pv'] + 3, char['pv_max'])
                await respond(f"**{char['nom']}** se repose et récupère des PV !")

            elif capacite['nom'] == "Musique de combat":
                for ally in self.player_state['inventaire']:
                    if ally and "Envoûté" not in ally.get("statuts", []): ally['attaque'] += 1
                if self.player_state['terrain'] and "Envoûté" not in self.player_state['terrain'].get("statuts", []):
                    self.player_state['terrain']['attaque'] += 1
                await respond(f"La **Musique de combat** motive vos troupes !")

            elif capacite['nom'] == "Boule de feu":
                if "statuts" not in char: char["statuts"] = []
                if "Incantation" not in char["statuts"]: char["statuts"].append("Incantation")
                await respond(f"**{char['nom']}** commence une incantation de Boule de feu !")

            elif capacite['nom'] == "Petit effort":
                if "statuts" not in char: char["statuts"] = []
                if "Sommeil" not in char["statuts"]: char["statuts"].append("Sommeil")
                await respond(f"**{char['nom']}** se prépare pour un 'Petit effort'.")

            elif capacite['nom'] == "Bouclier coton":
                if "statuts" not in char: char["statuts"] = []
                if "Coton" not in char["statuts"]: char["statuts"].append("Coton")
                await respond(f"**{char['nom']}** active son Bouclier Coton !")

            elif capacite['nom'] == "Oeuvre d'art":
                choice_view = ArtisteChoiceView()
                await respond("Quelle oeuvre d'art voulez-vous créer ?", view=choice_view)
                await choice_view.wait()
                if choice_view.choice:
                    if "statuts" not in char: char["statuts"] = []
                    if choice_view.choice == "abstrait":
                        if "Art contemporain" in char["statuts"]: char["statuts"].remove("Art contemporain")
                        if "Art abstrait" not in char["statuts"]: char["statuts"].append("Art abstrait")
                    elif choice_view.choice == "contemporain":
                        if "Art abstrait" in char["statuts"]: char["statuts"].remove("Art abstrait")
                        if "Art contemporain" not in char["statuts"]: char["statuts"].append("Art contemporain")
                else:
                    self.player_state['pr'] += actual_cost

            elif capacite['nom'] == "Revêtement":
                target_view = TargetSelectionView(self.player_state, user_char_slot=slot_index)
                if not target_view.children:
                    self.player_state['pr'] += actual_cost
                    return await respond("Il n'y a aucune autre allié à cibler.")
                await respond("Choisissez un personnage à équiper :", view=target_view)
                await target_view.wait()
                if target_view.chosen_target_id is not None:
                    target_id = target_view.chosen_target_id
                    target_char = self.player_state['terrain'] if target_id == "terrain" else self.player_state['inventaire'][int(target_id)]
                    if self._is_attack_blocked_by_enchantment(target_char):                        
                        await respond(f"👻 **{target_char['nom']}** est Envoûté ! L'équipement de la Cape est bloqué !")                        
                        self.player_state['pr'] += actual_cost                    
                    else:
                        if "statuts" not in target_char: target_char["statuts"] = []
                        target_char["statuts"].append("Cape Guerrière")
                        target_char['pv'] += char['pv']
                        target_char['attaque'] += char['attaque']
                        self.player_state['inventaire'][slot_index] = None
                else:
                    self.player_state['pr'] += actual_cost

            elif capacite['nom'] == "Pluie battante":
                if "statuts" not in char: char["statuts"] = []
                if "Parapluie" not in char["statuts"]: char["statuts"].append("Parapluie")
                await respond(f"☔ **{char['nom']}** active Pluie battante !")

            elif capacite['nom'] == "Contre-attaque":
                if "statuts" not in char: char["statuts"] = []
                if "Contre" not in char["statuts"]: char["statuts"].append("Contre")
                await respond(f"⚔️ **{char['nom']}** active sa contre-attaque !")

            elif capacite['nom'] == "Souvenir inoubliable":
                if "statuts" not in char: char["statuts"] = []
                if "Cadeau de Noël" not in char["statuts"]: char["statuts"].append("Cadeau de Noël")
                await respond(f"🎄 **{char['nom']}** active Souvenir inoubliable !")

            elif capacite['nom'] == "Evolution":
                try:
                    empty_slot = self.player_state['inventaire'].index(None)
                except ValueError:
                    self.player_state['pr'] += actual_cost
                    return await respond("Votre inventaire est plein, impossible d'évoluer.")
                evolution_level = 1
                if "+" in char['nom']:
                    try:
                        current_level = int(char['nom'].split("+")[1])
                        evolution_level = current_level + 1
                    except (ValueError, IndexError):
                        pass
                new_fourmi = {"nom": f"Fourmi chimère+{evolution_level}", "pv": char['pv'] + 1, "pv_max": char['pv_max'] + 1, "attaque": char['attaque'] + 1, "capacite": capacite}
                self.player_state['inventaire'][empty_slot] = new_fourmi
                await respond(f"🐜 **{char['nom']}** évolue et invoque une **Fourmi chimère+{evolution_level}** !")

            elif capacite['nom'] == "Gros câlin":
                if "statuts" not in char: char["statuts"] = []
                if "Calin" not in char["statuts"]: char["statuts"].append("Calin")
                await respond(f"🤗 **{char['nom']}** active Gros câlin !")

            elif capacite['nom'] == "Garde du corps":
                if "statuts" not in char: char["statuts"] = []
                if "Garde du corps" not in char["statuts"]:
                    char["statuts"].append("Garde du corps")
                    char["nb_gardes"] = 1
                else:
                    char["nb_gardes"] = char.get("nb_gardes", 1) + 1
                await respond(f"💂 **{char['nom']}** obtient un garde du corps ! ({char['nb_gardes']} au total)")

            elif capacite['nom'] == "Bourrasque":
                if "statuts" not in char: char["statuts"] = []
                if "Typhon" not in char["statuts"]: char["statuts"].append("Typhon")
                await respond(f"🌪️ **{char['nom']}** active Bourrasque !")

            # Dans cogs/game_1v1_manager.py, dans la méthode use_ability_callback

            elif capacite['nom'] == "Bourdonnement":
                if "statuts" not in char: char["statuts"] = []
                if "Bourdonnement" not in char["statuts"]: char["statuts"].append("Bourdonnement")
                
                opponent_state = next(p_state for p_id, p_state in self.game_state['players'].items() if p_id != interaction.user.id)
                
                # --- BLOC CORRIGÉ AVEC LA RÈGLE D'OR ---
                if not opponent_state.get('is_ai'):
                    try:
                        dm_channel = opponent_state['member'].dm_channel or await opponent_state['member'].create_dm()
                        temp_message = await dm_channel.send(f"🐝 Alerte! Le **Gros bourdon** de {interaction.user.display_name} vous a ciblé!")
                        asyncio.create_task(self._delete_message_after(temp_message, 10))
                    except discord.Forbidden: 
                        pass
                # --- FIN DE LA CORRECTION ---
                
                await respond(f"🐝 **{char['nom']}** active son Bourdonnement!")

            elif capacite['nom'] == "Soin rapide":
                pr_to_use = self.player_state['pr'] + actual_cost
                if pr_to_use == 0:
                    self.player_state['pr'] += actual_cost
                    return await respond("Vous n'avez aucun PR à convertir en HP!")
                hp_gain = pr_to_use * 2
                self.player_state['pr'] = 0
                self.player_state['hp'] = min(50, self.player_state['hp'] + hp_gain)
                char['pv'] -= 1
                message = f"🧪 **{char['nom']}** convertit vos {pr_to_use} PR en {hp_gain} HP!"
                if char['pv'] <= 0:
                    message += " Elle s'évapore après avoir donné sa dernière goutte..."
                    self.player_state['inventaire'][slot_index] = None
                await respond(message)

            elif capacite['nom'] == "Entrainement":
                if self._is_attack_blocked_by_enchantment(char):                    
                    await respond(f"👻 **{char['nom']}** est Envoûté ! L'augmentation d'attaque est bloquée !")
                else:
                    char['attaque'] += 3
                    await respond(f"💪 **{char['nom']}** gagne +3 en attaque !")

            elif capacite['nom'] == "Esprit robuste":
                # --- ÉTAPE 1 : Retirer la fatigue ---
                try:
                    print("yay - avant respond")
                    
                    self.player_state['pr'] += 5
                    if "Fatigue d'invocation" in char.get("statuts", []): 
                        char["statuts"].remove("Fatigue d'invocation")
                    if self.player_state['terrain'] != char:
                        if self.player_state['terrain']:
                            self.player_state['inventaire'][slot_index], self.player_state['terrain'] = self.player_state['terrain'], char
                        else:
                            self.player_state['inventaire'][slot_index] = None
                            self.player_state['terrain'] = char
                    self.player_state['has_placed_character'] = True
                    self.player_state['is_ready'] = True
                    
                    print("yay - prêt d'appeler respond")
                    
                    # ✅ C'EST ICI QUE ÇA CRASH
                    await respond(f"🧘 **{char['nom']}** utilise Esprit robuste ! Vous gagnez 5 PR et êtes prêt !")
                    
                    print("c ok - après respond")
                    
                    channel = self.manager_cog.bot.get_channel(self.game_state['channel_id'])
                    if channel:
                        await channel.send(f"🧘 **{interaction.user.display_name}** est automatiquement prêt grâce à son **Moine** !")
                    
                    await self.manager_cog.update_all_dashboards(self.game_state, locked=True)
                    other_player_ready = any(p['is_ready'] for pid, p in self.game_state['players'].items() if pid != interaction.user.id)
                    if other_player_ready and 'ready_view' in self.game_state:
                        self.game_state['ready_view'].stop()
                        
                except Exception as e:
                    print(f"[ERROR MOINE] Exception rencontrée : {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    await interaction.followup.send(f"❌ Erreur Moine: {str(e)}", ephemeral=True)
            elif capacite['nom'] == "Inséparable":
                try:
                    empty_slot = self.player_state['inventaire'].index(None)
                except ValueError:
                    self.player_state['pr'] += actual_cost
                    return await respond("Votre inventaire est plein, impossible de se séparer.")
                homme = {"nom": "Homme", "pv": 5, "pv_max": 5, "attaque": 5}
                femme = {"nom": "Femme", "pv": 5, "pv_max": 5, "attaque": 5}
                self.player_state['inventaire'][slot_index] = homme
                self.player_state['inventaire'][empty_slot] = femme
                await respond(f"💑 Le **{char['nom']}** se sépare en **Homme** et **Femme** !")

            elif capacite['nom'] == "Spores":
                if "statuts" not in char: char["statuts"] = []
                if "Champignon" not in char["statuts"]: char["statuts"].append("Champignon")
                await respond(f"🍄 **{char['nom']}** prépare ses spores toxiques !")

            elif capacite['nom'] == "Monologue ennuyeux":
                if "statuts" not in char: char["statuts"] = []
                if "blablabla" not in char["statuts"]: char["statuts"].append("blablabla")
                await respond(f"💬 **{char['nom']}** commence son monologue !")

            elif capacite['nom'] == "Piratage":
                # La capacité prépare un effet pour le prochain tour
                if "statuts" not in char: char["statuts"] = []
                # On ajoute "Piratage" pour que le joueur sache que c'est en cours
                if "Piratage" not in char["statuts"]:
                    char["statuts"].append("Piratage")
                
                # On met un drapeau sur le joueur pour le retrouver au prochain tour
                self.player_state['piratage_pending'] = True
                await respond("💻 Piratage initialisé ! Vous pourrez supprimer un personnage de l'inventaire adverse au début du prochain tour.")

            elif capacite['nom'] == "Prière":
                target_view = TargetSelectionView(self.player_state, user_char_slot=slot_index)
                if not target_view.children:
                    self.player_state['pr'] += actual_cost
                    return await respond("Il n'y a aucun allié à cibler.")
                await respond("Choisissez un allié à guérir :", view=target_view)
                await target_view.wait()
                if target_view.chosen_target_id is not None:
                    target_id = target_view.chosen_target_id
                    target_char = self.player_state['terrain'] if target_id == "terrain" else self.player_state['inventaire'][int(target_id)]
                    negative_statuses = [s for s in target_char.get("statuts", []) if s in ["Empoisonné", "Malédiction", "Envoûté"]]
                    if not negative_statuses:
                        self.player_state['pr'] += actual_cost
                        return await interaction.followup.send(f"**{target_char['nom']}** n'a aucun statut négatif.", ephemeral=True)
                    status_view = StatusRemovalView(target_char)
                    await interaction.followup.send("Choisissez un statut à guérir :", view=status_view, ephemeral=True)
                    await status_view.wait()
                    if status_view.chosen_status:
                        target_char["statuts"].remove(status_view.chosen_status)
                        if status_view.chosen_status == "Envoûté" and "attaque_originale" in target_char:
                            target_char["attaque"] = target_char["attaque_originale"]
                            del target_char["attaque_originale"]
                        await interaction.followup.send(f"🙏 Le statut **{status_view.chosen_status}** a été retiré de **{target_char['nom']}** !", ephemeral=True)
                    else:
                        self.player_state['pr'] += actual_cost
                else:
                    self.player_state['pr'] += actual_cost

            elif capacite['nom'] == "Vol":
                if "statuts" not in char: char["statuts"] = []
                if "Vol" not in char["statuts"]: char["statuts"].append("Vol")
                await respond(f"🐝 **{char['nom']}** se prépare à voler !")

            elif capacite['nom'] == "Nuisible":
                if "statuts" not in char: char["statuts"] = []
                if "Malicieux" not in char["statuts"]: char["statuts"].append("Malicieux")
                await respond(f"🦝 **{char['nom']}** prépare un tour sournois !")

        finally:
            # IMPORTANT : Toujours mettre à jour le dashboard à la fin, quel que soit le chemin pris
            await asyncio.sleep(0.1)        
            await self.manager_cog.update_all_dashboards(self.game_state)
            
# Vue pour gérer l'invitation au duel
class DuelInvitationView(discord.ui.View):
    def __init__(self, manager_cog, challenger: discord.Member, opponent: discord.Member):
        super().__init__(timeout=180) # L'invitation expire après 3 minutes
        self.manager_cog = manager_cog
        self.challenger = challenger
        self.opponent = opponent
        self.result = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # On s'assure que seule la personne défiée peut cliquer
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Vous n'êtes pas la personne défiée.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accepter le Duel", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"✅ {self.opponent.mention} a accepté le duel de {self.challenger.mention} !", view=self)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"❌ {self.opponent.mention} a refusé le duel.", view=self)



class Game1v1ManagerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_games = {}
        
        self.passives = {        
                "second_chance": {            
                    "name": "Deuxième chance",            
                    "description": "Quand vous tombez à 0 HP ou moins, vous ne perdez pas et regagnez instantanément 20 HP. Ne fonctionne qu'une fois.",            
                    "emoji": "🔄"        },     
                "absenteism": {            
                    "name": "Absentéisme",            
                    "description": "Si vous n'avez pas de personnage sur le terrain pour le prochain combat, vous recevez +4 PR pour votre prochaine phase de préparation.",            
                    "emoji": "💸"        },
                "human_tide": {            
                    "name": "Tactique de la marée humaine",            
                    "description": "Au début de la phase de préparation, si votre inventaire est complet (3 personnages), tous vos personnages dans l'inventaire gagnent +3 en attaque.",            
                    "emoji": "👥"        },
                "maitre_capacites": {                    
                    "name": "Maître des capacités",                    
                    "description": "Toutes les 2 capacités utilisées, la troisième est gratuite. Le compteur ne se réinitialise pas entre les tours.",                    
                    "emoji": "🧙"                },
                "pret": {                
                    "name": "Prêt",                
                    "description": "Permet d'emprunter des PR une fois par tour, mais attention au remboursement !",                
                    "emoji": "🏦"            },
                "mode_facile": {                
                    "name": "Mode facile",                
                    "description": "Au lieu de gagner 4 PR passivement à la fin de chaque tour, vous en gagnez 6.",                
                    "emoji": "😎"            },
                "promotion": {                
                    "name": "Promotion",                
                    "description": "Les personnages coûtant entre 6 et 8 PR voient le coût de leur capacité réduit à 1 PR.",                
                    "emoji": "🏷️"},
                "a_main_nue": {                
                    "name": "À main nue",                
                    "description": "Vos personnages gagnent +5 PV max à l'invocation. Ce bonus est retiré après l'utilisation de leur capacité.",                
                    "emoji": "👊"            },
                "vif": {                
                    "name": "Vif",                
                    "description": "Vous avez toujours l'initiative. Si vous l'auriez eue de toute façon, votre personnage effectue une attaque bonus avant le début du combat.",                
                    "emoji": "⚡"           
                    },
                "volonte": {               
                    "name": "Volonté",                
                    "description": "Au combat, vos personnages survivent à la première attaque qui devrait les tuer avec 1 PV. Se réinitialise à chaque combat.",                
                    "emoji": "💎"            }
        }
        
        self.ai = AITrainer(self.bot)
        
        # Dans cogs/game_1v1_manager.py, classe Game1v1ManagerCog

    # Dans cogs/game_1v1_manager.py, classe Game1v1ManagerCog

    # Dans cogs/game_1v1_manager.py, classe Game1v1ManagerCog

    async def _handle_ai_preparation_turn(self, player_state, game_state):
        """
        Gère le tour de préparation pour l'IA de manière stratégique et adaptative.
        L'IA analyse l'adversaire, évalue la situation et prend des décisions en conséquence.
        """
        # --- ÉTAPE 0 : Initialisation et Analyse ---
        await asyncio.sleep(random.uniform(2.5, 4.5)) # Simule un temps de réflexion
        
        channel = self.bot.get_channel(game_state['channel_id'])
        
        # Récupère l'état de l'adversaire pour l'analyse, c'est la clé de l'intelligence
        ai_player_id = player_state['member'].id
        opponent_id = next((pid for pid in game_state['players'] if pid != ai_player_id), None)
        opponent_state = game_state['players'].get(opponent_id)

        if not opponent_state:
            print("[IA ERROR] Impossible de trouver l'adversaire. L'IA passera son tour.")
            player_state['is_ready'] = True
            await self.update_all_dashboards(game_state)
            return

        print(f"--- TOUR DE L'IA (Tour {game_state['tour']}) ---")

        # --- ÉTAPE 1 : Logique Spécifique au Tour 1 (Ouverture) ---
        if game_state['tour'] == 1:
            print("[IA STRATÉGIE] Phase d'ouverture : Remplir l'inventaire et placer un tank.")
            # Invoquer autant que possible pour remplir l'inventaire
            while player_state['pr'] > 0 and None in player_state['inventaire']:
                choices = self.ai.generer_choix_invocation(player_state)
                if not choices:
                    break
                
                # Le choix d'invocation est déjà intelligent grâce à la nouvelle méthode
                char_to_invoke = self.ai.choisir_personnage_invocation(
                    choices, player_state, opponent_state, game_state
                )
                if not char_to_invoke or char_to_invoke['cout'] > player_state['pr']:
                    continue # S'assure de ne pas invoquer si le coût est trop élevé après un choix intelligent
                
                char_data = copy.deepcopy(char_to_invoke)
                if 'pv_max' not in char_data:
                    char_data['pv_max'] = char_data['pv']
                
                player_state['pr'] -= char_data['cout']
                empty_slot = player_state['inventaire'].index(None)
                player_state['inventaire'][empty_slot] = char_data
                
            # Placer le meilleur personnage pour commencer (sera défensif grâce à la nouvelle logique)
            self.ai.placer_strategiquement(player_state, opponent_state, game_state)

        # --- ÉTAPE 2 : Logique pour les tours suivants (Adaptation) ---
        else:
            print("[IA STRATÉGIE] Phase d'adaptation.")
            # ORDRE DE PRIORITÉ DES ACTIONS :
            # 1. Utiliser une capacité pour préparer le terrain.
            # 2. Invoquer pour combler les vides.
            # 3. Placer/Remplacer le personnage sur le terrain pour optimiser le combat.

            # Action 1: Utiliser une capacité de manière intelligente
            if player_state['pr'] >= 2: # Seuil minimum pour envisager une capacité
                self.ai.utiliser_capacite_smart(player_state, opponent_state, game_state)
            
            # Action 2: Invoquer un personnage si un slot est libre et que les PR le permettent
            if player_state['pr'] > 0 and None in player_state['inventaire']:
                choices = self.ai.generer_choix_invocation(player_state)
                if choices:
                    char_to_invoke = self.ai.choisir_personnage_invocation(
                        choices, player_state, opponent_state, game_state
                    )
                    if char_to_invoke and char_to_invoke['cout'] <= player_state['pr']:
                        char_data = copy.deepcopy(char_to_invoke)
                        if 'pv_max' not in char_data:
                            char_data['pv_max'] = char_data['pv']
                        
                        # Ajout de la fatigue d'invocation pour les tours > 1
                        if "statuts" not in char_data:
                            char_data["statuts"] = []
                        char_data["statuts"].append("Fatigue d'invocation")
                        
                        player_state['pr'] -= char_data['cout']
                        empty_slot = player_state['inventaire'].index(None)
                        player_state['inventaire'][empty_slot] = char_data

            # Action 3: Placer/Remplacer le personnage sur le terrain de manière optimale
            self.ai.placer_strategiquement(player_state, opponent_state, game_state)

        # --- ÉTAPE 3 : Finalisation du tour ---
        player_state['is_ready'] = True
        print("--- FIN DU TOUR DE L'IA ---")
        await self.update_all_dashboards(game_state)
        
        
    # Dans cogs/game_1v1_manager.py, classe Game1v1ManagerCog

    # AJOUTEZ CETTE NOUVELLE MÉTHODE
    async def _offer_passive_selection(self, game_state):
        """Orchestre l'offre de passifs aux deux joueurs en parallèle."""
        tasks = []
        for player_id, player_state in game_state['players'].items():
            # Crée une tâche pour chaque joueur (humain ou IA)
            task = self._offer_passive_to_player(player_id, player_state, game_state)
            tasks.append(task)
        
        # Exécute les offres de passifs en parallèle pour que les deux joueurs reçoivent le message en même temps
        await asyncio.gather(*tasks)
        await self.update_all_dashboards(game_state)
    # Dans cogs/game_1v1_manager.py, classe Game1v1ManagerCog

    # REMPLACEZ L'ANCIENNE MÉTHODE PAR CELLE-CI
    async def _offer_passive_to_player(self, player_id, player_state, game_state):
        """Propose un choix de passifs à un joueur ou simule ce choix pour l'IA."""
        
        # --- Logique commune de sélection des 3 passifs ---
        if 'passives' not in player_state:
            player_state['passives'] = {}
        
        available_passives = {}
        for passive_id, passive_info in self.passives.items():
            if game_state['tour'] == 5 and passive_id in player_state['passives']:
                continue
            available_passives[passive_id] = passive_info
        
        if len(available_passives) > 3:
            passive_ids = random.sample(list(available_passives.keys()), 3)
            selected_passives = {pid: available_passives[pid] for pid in passive_ids}
        else:
            selected_passives = available_passives

        # --- Branche de logique : IA vs Humain ---
        if player_state.get('is_ai'):                
            # L'IA choisit selon sa priorité + contexte    
            if selected_passives:        
                # Trouver l'adversaire pour le contexte        
                opponent_id = next((pid for pid in game_state['players']                           
                                    if pid != player_state['member'].id), None)        
                opponent_state = game_state['players'][opponent_id] if opponent_id else None                
                self.ai.choisir_passif(player_state, selected_passives, game_state)                    
                return
        
        # Si c'est un humain, on continue avec l'interface visuelle
        member = player_state['member']
        message_content = f"**Tour {game_state['tour']} - Choisissez un passif:**\n\n"
        for passive_id, passive_info in selected_passives.items():
            message_content += f"**{passive_info['name']}** {passive_info['emoji']}: {passive_info['description']}\n\n"
        
        view = PassiveSelectionView(selected_passives)
        try:
            dm_channel = member.dm_channel or await member.create_dm()
            await dm_channel.send(message_content, view=view)
            await view.wait()
            
            if view.chosen_passive:
                player_state['passives'][view.chosen_passive] = True
                passive_info = self.passives[view.chosen_passive]
                await dm_channel.send(f"Vous avez obtenu le passif **{passive_info['name']}** {passive_info['emoji']}!")
            else:
                random_passive = random.choice(list(selected_passives.keys()))
                player_state['passives'][random_passive] = True
                passive_info = self.passives[random_passive]
                await dm_channel.send(f"Vous n'avez pas fait de choix à temps. Le passif **{passive_info['name']}** {passive_info['emoji']} vous a été attribué aléatoirement.")
        
        except discord.Forbidden:
            random_passive = random.choice(list(selected_passives.keys()))
            player_state['passives'][random_passive] = True
        
    def check_and_remove_dead_character(self, player_state, char, slot=None, message=None):
        """
        Vérifie si un personnage doit être retiré du jeu car ses PV sont à 0 ou moins.
    
        Args:
            player_state: État du joueur
            char: Personnage à vérifier
            slot: Emplacement du personnage dans l'inventaire (None si sur le terrain)
            message: Message à afficher si le personnage est détruit (optionnel)
        
        Returns:
            bool: True si le personnage a été retiré, False sinon
        """
        if char and char['pv'] <= 0:
            # Message par défaut si aucun n'est fourni
            if message is None:
                message = f"**{char['nom']}** a été détruit car ses PV sont tombés à 0 ou moins."
        
            # Retirer le personnage de l'inventaire ou du terrain
            if slot is not None:
                player_state['inventaire'][slot] = None
            else:
                player_state['terrain'] = None
            
            return True
        return False
    
        # Dans cogs/game_1v1_manager.py, classe Game1v1ManagerCog

    # ... (après la méthode check_and_remove_dead_character) ...

    '''@app_commands.command(name="duel_ia", description="Entraînez-vous en défiant une IA.")
    async def duel_ia(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if interaction.channel.id in self.active_games:
            return await interaction.response.send_message("Une partie de duel est déjà en cours dans ce salon.", ephemeral=True)

        player1 = interaction.user
        # L'IA n'a pas de vrai membre Discord, on va simuler
        await self._start_new_duel(interaction, player1, None) # On passe None pour l'adversaire'''


    # --- Commandes et logique de démarrage ---
    @app_commands.command(name="duel", description="Défie un autre joueur dans un duel stratégique.")
    @app_commands.describe(adversaire="Le joueur que vous voulez défier.")
    async def duel(self, interaction: discord.Interaction, adversaire: discord.Member):
        if adversaire.id == interaction.user.id:
            return await interaction.response.send_message("Vous ne pouvez pas vous défier vous-même.", ephemeral=True)
        if adversaire.bot:
            return await interaction.response.send_message("Vous ne pouvez pas défier un bot.", ephemeral=True)
        if interaction.channel.id in self.active_games:
            return await interaction.response.send_message("Une partie de duel est déjà en cours dans ce salon.", ephemeral=True)

        view = DuelInvitationView(self, interaction.user, adversaire)
        await interaction.response.send_message(f"⚔️ {interaction.user.mention} défie {adversaire.mention} en duel ! {adversaire.mention}, vous avez 3 minutes pour répondre.", view=view)
        
        await view.wait()

        if view.result is True:
            await self._start_new_duel(interaction, interaction.user, adversaire)
        elif view.result is False:
            pass
        else:
            message = await interaction.original_response()
            await message.edit(content="L'invitation au duel a expiré.", view=None)

    # Dans cogs/game_1v1_manager.py, classe Game1v1ManagerCog

    async def _start_new_duel(self, interaction: discord.Interaction, player1: discord.Member, player2: discord.Member):
        
        is_ai_game = player2 is None
        # Création de l'objet joueur pour l'IA
        if is_ai_game:
            ai_id = 1 # Un ID simple, car il n'y a pas de vrai utilisateur
            ai_member_mock = type('obj', (object,), {'display_name': 'IA (Gorille)', 'mention': '**IA (Gorille)**', 'id': ai_id})
            player2_id = ai_id
            player2_member = ai_member_mock
        else:
            player2_id = player2.id
            player2_member = player2
        
        game_state = {
            'channel_id': interaction.channel.id,
            'players': {
                player1.id: { 'member': player1, 'hp': 50, 'pr': 8, 'inventaire': [None, None, None], 'terrain': None, 'is_ready': False, 'last_dm_id': None, 'passives': {},'has_placed_character': False,'ability_usage_counter': 0, 'dette': 0,'a_emprunte_ce_tour': False,'piratage_pending': False,'is_ai': False},
                # --- CORRECTION ICI ---
                player2_id: { 'member': player2_member, 'hp': 50, 'pr': 8, 'inventaire': [None, None, None], 'terrain': None,'is_ready': False, 'last_dm_id': None, 'passives': {},'has_placed_character': False, 'ability_usage_counter': 0,'dette': 0,'a_emprunte_ce_tour': False,'piratage_pending': False,  'is_ai': is_ai_game}
            },
            'phase': 'preparation',
            'tour': 1
        }
        self.active_games[interaction.channel.id] = game_state

        # --- CORRECTION ICI ---
        await interaction.followup.send(f"La partie entre {player1.mention} et {player2_member.mention} commence ! La première phase de préparation débute. Vérifiez vos messages privés !")
        
        asyncio.create_task(self.run_duel_loop(game_state))

    # --- Boucle de jeu principale ---
    # cogs/game_1v1_manager.py (dans la classe Game1v1ManagerCog)

    # --- Boucle de jeu principale ---
    async def run_duel_loop(self, game_state):
        player_ids = list(game_state['players'].keys())
        p1_id, p2_id = player_ids[0], player_ids[1]

        # La boucle continue tant que les deux joueurs ont des HP
        while True:
            # Exécution des phases de préparation et de combat
            if game_state['phase'] == 'preparation':
                await self.preparation_phase(game_state)
                game_state['phase'] = 'combat'

            if game_state['phase'] == 'combat':
                combat_engine = CombatEngine(self, game_state)
                await combat_engine.run_combat()
                
                # Vérifier si un joueur a perdu tous ses HP après le combat
                p1_state = game_state['players'][p1_id]
                p2_state = game_state['players'][p2_id]
                
                # Vérifier le passif "Deuxième chance" pour le joueur 1
                if p1_state['hp'] <= 0:
                    if ('passives' in p1_state and 'second_chance' in p1_state['passives'] 
                        and p1_state['passives']['second_chance'] == True):
                        # Activer le passif
                        p1_state['hp'] = 20
                        p1_state['passives']['second_chance'] = False  # Désactiver après utilisation
                        channel = self.bot.get_channel(game_state['channel_id'])
                        await channel.send(f"🔄 **{p1_state['member'].display_name}** active son passif Deuxième chance et regagne 20 HP!")
                
                # Vérifier le passif "Deuxième chance" pour le joueur 2
                if p2_state['hp'] <= 0:
                    if ('passives' in p2_state and 'second_chance' in p2_state['passives'] 
                        and p2_state['passives']['second_chance'] == True):
                        # Activer le passif
                        p2_state['hp'] = 20
                        p2_state['passives']['second_chance'] = False  # Désactiver après utilisation
                        channel = self.bot.get_channel(game_state['channel_id'])
                        await channel.send(f"🔄 **{p2_state['member'].display_name}** active son passif Deuxième chance et regagne 20 HP!")
                
                # Vérifier à nouveau si un joueur a perdu après l'application des passifs
                if p1_state['hp'] <= 0 or p2_state['hp'] <= 0:
                    break  # Sortir de la boucle si un joueur a toujours 0 HP ou moins
            
        # Fin de la partie (quelqu'un a gagné)
        channel = self.bot.get_channel(game_state['channel_id'])
        winner = None
        if game_state['players'][p1_id]['hp'] <= 0:
            winner = game_state['players'][p2_id]['member']
        else:
            winner = game_state['players'][p1_id]['member']
        
        await channel.send(f"La partie est terminée ! Victoire de {winner.mention} !")
        del self.active_games[game_state['channel_id']]

        # Dans cogs/game_1v1_manager.py, classe Game1v1ManagerCog

    async def preparation_phase(self, game_state):
        # ✅ --- NOUVEAU BLOC POUR GÉRER LE PIRATAGE ---
        piratage_tasks = []
        for p_id, p_state in game_state['players'].items():
            if p_state.get('piratage_pending'):
                # Trouver l'adversaire
                opponent_state = next(o_state for o_id, o_state in game_state['players'].items() if o_id != p_id)
                # On lance la gestion du piratage en tâche de fond pour ne pas bloquer
                task = self._handle_piratage_execution(p_state, opponent_state)
                piratage_tasks.append(task)
        
        # On attend que tous les piratages soient résolus
        if piratage_tasks:
            await asyncio.gather(*piratage_tasks)
        # --- FIN DU NOUVEAU BLOC ---

        game_state['phase'] = 'preparation'
        # ... (le reste de la méthode ne change pas)
        
        game_state['phase'] = 'preparation'
        
        # Réinitialiser les statuts de tour et gérer le remboursement
        for p_id, p_state in game_state['players'].items():
            p_state['is_ready'] = False
            p_state['has_placed_character'] = False
            if p_state['terrain']:
               p_state['has_placed_character'] = True
            
            # AJOUT : Réinitialiser le flag d'emprunt pour le tour
            p_state['a_emprunte_ce_tour'] = False

            # AJOUT : Logique de remboursement de la dette
            if p_state.get('dette', 0) < 0:
                dette_absolue = abs(p_state['dette'])
                
                # Calcul du prélèvement selon vos règles
                prelevement_brut = round(dette_absolue * 0.40)
                prelevement_final = max(4, prelevement_brut) # Minimum de 4 PR
                
                # Si la dette est inférieure au prélèvement minimum, on prélève juste la dette
                if dette_absolue < prelevement_final:
                    prelevement_final = dette_absolue

                pr_actuels = p_state['pr']
                
                if pr_actuels >= prelevement_final:
                    # Le joueur a assez de PR
                    p_state['pr'] -= prelevement_final
                    p_state['dette'] += prelevement_final
                    remboursement_msg = f"🏦 Un prélèvement de **{prelevement_final} PR** a été effectué pour rembourser votre dette."
                else:
                    # Le joueur n'a pas assez de PR
                    pr_manquant = prelevement_final - pr_actuels
                    hp_perdus = pr_manquant * 3
                    
                    p_state['pr'] = 0 # Il perd tous ses PR
                    p_state['hp'] -= hp_perdus
                    
                    # On met à jour la dette avec ce qui a été payé en PR
                    p_state['dette'] += pr_actuels 
                    
                    remboursement_msg = (f"🏦 Vous n'aviez pas assez de PR pour le prélèvement de **{prelevement_final} PR**.\n"
                                       f"Vous avez payé **{pr_actuels} PR** et perdu **{hp_perdus} HP** pour couvrir le reste.")

                # Informer le joueur en MP
                if not p_state.get('is_ai'):
                    try:
                        dm_channel = p_state['member'].dm_channel or await p_state['member'].create_dm()
                        await dm_channel.send(remboursement_msg)
                    except discord.Forbidden:
                        pass  
        if game_state['tour'] == 2 or game_state['tour'] == 5:        
            await self._offer_passive_selection(game_state)
        
        # Appliquer les effets d'empoisonnement
        for p_id, p_state in game_state['players'].items():
            # Vérifier les personnages dans l'inventaire
            for i, inv_char in enumerate(p_state['inventaire']):
                if inv_char and "statuts" in inv_char and "Empoisonné" in inv_char["statuts"]:
                    # Appliquer 2 points de dégâts
                    inv_char['pv'] -= 2
                    if not p_state.get('is_ai'):
                        try:
                            dm_channel = p_state['member'].dm_channel or await p_state['member'].create_dm()
                            await dm_channel.send(f"☠️ **{inv_char['nom']}** subit 2 points de dégâts du poison ! (PV restants : {max(0, inv_char['pv'])})")
                        except discord.Forbidden:
                            pass
                    
                    # Vérifier si le personnage est mort
                    if inv_char['pv'] <= 0:
                        message = f"☠️ **{inv_char['nom']}** a succombé au poison !"
                        self.check_and_remove_dead_character(p_state, inv_char, slot=i, message=message)
                        if not p_state.get('is_ai'):
                            try:
                                dm_channel = p_state['member'].dm_channel or await p_state['member'].create_dm()
                                await dm_channel.send(message)
                            except discord.Forbidden:
                                pass
            
            # Vérifier le personnage sur le terrain
            terrain_char = p_state['terrain']
            if terrain_char and "statuts" in terrain_char and "Empoisonné" in terrain_char["statuts"]:
                # Appliquer 2 points de dégâts
                terrain_char['pv'] -= 2
                if not p_state.get('is_ai'):
                    try:
                        dm_channel = p_state['member'].dm_channel or await p_state['member'].create_dm()
                        await dm_channel.send(f"☠️ **{terrain_char['nom']}** subit 2 points de dégâts du poison ! (PV restants : {max(0, terrain_char['pv'])})")
                    except discord.Forbidden:
                        pass
                
                # Vérifier si le personnage est mort
                if terrain_char['pv'] <= 0:
                    message = f"☠️ **{terrain_char['nom']}** a succombé au poison !"
                    self.check_and_remove_dead_character(p_state, terrain_char, slot=None, message=message)
                    if not p_state.get('is_ai'):
                        try:
                            dm_channel = p_state['member'].dm_channel or await p_state['member'].create_dm()
                            await dm_channel.send(message)
                        except discord.Forbidden:
                            pass
        
        # Appliquer l'effet du Bourdonnement
        for p_id, p_state in game_state['players'].items():
            # Trouver l'adversaire
            opponent_id = None
            opponent_state = None
            for other_id, other_state in game_state['players'].items():
                if other_id != p_id:
                    opponent_id = other_id
                    opponent_state = other_state
                    break
            
            if opponent_state:
                # Vérifier si l'adversaire a des personnages avec le statut "Bourdonnement"
                for inv_char in opponent_state['inventaire']:
                    if inv_char and "statuts" in inv_char and "Bourdonnement" in inv_char["statuts"]:
                        # Réduire les PR du joueur actuel de 3 (minimum 0)
                        p_state['pr'] = max(0, p_state['pr'] - 3)
                        
                        if not p_state.get('is_ai'):
                            try:
                                dm_channel = p_state['member'].dm_channel or await p_state['member'].create_dm()
                                await dm_channel.send(f"🐝 Le Bourdonnement du **Gros bourdon** vous fait perdre 3 PR! Vous avez maintenant {p_state['pr']} PR.")
                            except discord.Forbidden:
                                pass
                        
                        if not p_state.get('is_ai'):
                            try:
                                dm_channel = opponent_state['member'].dm_channel or await opponent_state['member'].create_dm()
                                await dm_channel.send(f"🐝 Votre **Gros bourdon** a fait perdre 3 PR à {p_state['member'].display_name}!")
                            except discord.Forbidden:
                                pass
                        
                        # Supprimer le statut après utilisation
                        inv_char["statuts"].remove("Bourdonnement")
                        break
                
                # Vérifier aussi le personnage sur le terrain
                terrain_char = opponent_state['terrain']
                if terrain_char and "statuts" in terrain_char and "Bourdonnement" in terrain_char["statuts"]:
                    # Réduire les PR du joueur actuel de 3 (minimum 0)
                    p_state['pr'] = max(0, p_state['pr'] - 3)
                    
                    # Envoyer un message au joueur
                    if not p_state.get('is_ai'):
                        try:
                            dm_channel = p_state['member'].dm_channel or await p_state['member'].create_dm()
                            await dm_channel.send(f"🐝 Le Bourdonnement du **Gros bourdon** vous fait perdre 3 PR! Vous avez maintenant {p_state['pr']} PR.")
                        except discord.Forbidden:
                            pass
                    
                    if not p_state.get('is_ai'):
                        try:
                            dm_channel = opponent_state['member'].dm_channel or await opponent_state['member'].create_dm()
                            await dm_channel.send(f"🐝 Votre **Gros bourdon** a fait perdre 3 PR à {p_state['member'].display_name}!")
                        except discord.Forbidden:
                            pass
                    
                    # Supprimer le statut après utilisation
                    terrain_char["statuts"].remove("Bourdonnement")

        # Envoyer les dashboards aux joueurs
        await self.update_all_dashboards(game_state)
        
        human_players = []        
        ai_players = []        
        for p_state in game_state['players'].values():            
            if p_state['is_ai']:                
                ai_players.append(p_state)            
            else:                
                human_players.append(p_state)        
            # On envoie les dashboards aux humains        
        await self.update_all_dashboards(game_state)        
            # On lance les tours des IA en parallèle        
        ai_tasks = [self._handle_ai_preparation_turn(p_state, game_state) for p_state in ai_players]        
        await asyncio.gather(*ai_tasks)
        
        
        channel = self.bot.get_channel(game_state['channel_id'])

        if human_players:
            # --- ÉTAPE 1 : ENVOYER LES DASHBOARDS DÉVERROUILLÉS ---
            await self.update_all_dashboards(game_state, locked=False)
            
            # --- ÉTAPE 2 : CRÉER LA VUE ET ENVOYER LE MESSAGE ---
            view = ReadyView(self, game_state)
            game_state['ready_view'] = view
            
            ready_message = await channel.send(
                f"**Tour {game_state['tour']} - Phase de Préparation.**\n"
                f"Organisez votre terrain et cliquez sur 'Prêt' !",
                view=view
            )
            
            # --- ÉTAPE 3 : ATTENDRE QUE LES DEUX JOUEURS SOIENT PRÊTS ---
            timeout = 0
            while timeout < 600:
                await asyncio.sleep(0.5)
                timeout += 0.5
                
                all_ready = all(p.get('is_ready', False) for p in game_state['players'].values())
                if all_ready:
                    break
            
            # --- ÉTAPE 4 : FORCER PRÊT POUR TIMEOUT ---
            for p_id, p_state in game_state['players'].items():
                if not p_state.get('is_ready'):
                    p_state['is_ready'] = True
            
            # --- ÉTAPE 5 : MAINTENANT VERROUILLER ---
            await self.update_all_dashboards(game_state, locked=True)
            
            try:
                await ready_message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        else:
            # Deux IA
            await self.update_all_dashboards(game_state, locked=True)

        await channel.send("Les deux joueurs sont prêts ! Le combat va commencer...")
        
        
    async def _handle_piratage_execution(self, player_state, opponent_state):
        """Gère le choix et la suppression d'un personnage via Piratage."""
        
        # Retirer le statut "Piratage" du personnage qui l'a lancé
        for char in player_state['inventaire']:
            if char and "Piratage" in char.get("statuts", []):
                char["statuts"].remove("Piratage")
                break # On suppose qu'un seul peut l'avoir

        # Récupérer les cibles valides (personnages non-vides dans l'inventaire adverse)
        targets = [char for char in opponent_state['inventaire'] if char is not None]
        if not targets:
            # Informer le joueur si l'adversaire n'a rien à voler
            if not player_state.get('is_ai'):
                try:
                    await (player_state['member'].dm_channel or await player_state['member'].create_dm()).send("💻 Votre Piratage n'a trouvé aucune cible dans l'inventaire adverse.")
                except discord.Forbidden: pass
            player_state['piratage_pending'] = False
            return

        # Logique pour le joueur humain
        if not player_state.get('is_ai'):
            view = PiratageTargetView(opponent_state['inventaire'])
            try:
                dm_channel = player_state['member'].dm_channel or await player_state['member'].create_dm()
                await dm_channel.send("💻 **Piratage Actif !** Choisissez un personnage à supprimer de l'inventaire de votre adversaire :", view=view)
                await view.wait()

                if view.chosen_slot_index is not None:
                    char_to_remove = opponent_state['inventaire'][view.chosen_slot_index]
                    opponent_state['inventaire'][view.chosen_slot_index] = None
                    
                    # Notifier les deux joueurs
                    await dm_channel.send(f"✅ Vous avez supprimé **{char_to_remove['nom']}** de l'inventaire adverse.")
                    if not opponent_state.get('is_ai'):
                        await (opponent_state['member'].dm_channel or await opponent_state['member'].create_dm()).send(f"🚨 **ALERTE !** Votre personnage **{char_to_remove['nom']}** a été supprimé par un Piratage !")

            except discord.Forbidden:
                pass # Le joueur a bloqué les MPs, l'action échoue silencieusement
        
        # TODO: Ajouter une logique pour l'IA si elle utilise le Piratage
        # Pour l'instant, elle choisira au hasard
        else:
            # L'IA choisit une cible au hasard
            possible_indices = [i for i, char in enumerate(opponent_state['inventaire']) if char is not None]
            if possible_indices:
                chosen_index = random.choice(possible_indices)
                char_to_remove = opponent_state['inventaire'][chosen_index]
                opponent_state['inventaire'][chosen_index] = None
                # Annonce publique dans le canal du jeu
                channel = self.bot.get_channel(self.active_games[player_state['member'].id]['channel_id'])
                await channel.send(f"💻 L'IA a piraté et supprimé **{char_to_remove['nom']}** de l'inventaire de **{opponent_state['member'].display_name}** !")


        # Réinitialiser le drapeau
        player_state['piratage_pending'] = False
    
    def _create_dashboard_embed(self, player_state, opponent_state, show_opponent=True):
        """Crée l'embed du dashboard pour un joueur."""
        embed = discord.Embed(title="Tableau de Bord - Duel", color=discord.Color.gold())
        stats_value = f"❤️ HP: {player_state['hp']}/50\n🤔 PR: {player_state['pr']}"    
        if player_state.get('dette', 0) < 0:        
            stats_value += f"\n💸 **À rembourser: {abs(player_state['dette'])} PR**"
        
        embed.add_field(name="Vos Stats",value=stats_value , inline=True)
        if show_opponent:
            embed.add_field(name="Stats Adversaire", value=f"❤️ HP: {opponent_state['hp']}/50\n🤔 PR: {opponent_state['pr']}", inline=True)
        else:        # Afficher un message indiquant que les stats de l'adversaire sont cachées        
            embed.add_field(name="Stats Adversaire", value="❓ Cachées pendant la phase de préparation", inline=True)
        if 'passives' in player_state and player_state['passives']:        
            passives_text = ""        
            for passive_id, active in player_state['passives'].items():            
                if active:  # Si le passif est actif                
                    passive_info = self.passives[passive_id]                
                    passives_text += f"{passive_info['emoji']} **{passive_info['name']}**: {passive_info['description']}\n"        
            if passives_text:            
                embed.add_field(name="Vos Passifs", value=passives_text, inline=False)
        STATUS_EMOJIS = {            
                        "Flotte": "☁️",            
                        "En chasse": "🎯",            
                        "Recherché": "📜",
                        "À l'affût": "🦊",
                        "Incantation": "🔥",
                        "Sommeil": "💤",
                        "Coton": "🛡️",
                        "Art abstrait": "🎨",      # NOUVELLE LIGNE                        
                        "Art contemporain": "🖼️",
                        "Cape Guerrière": "🧥",
                        "Parapluie": "☔",
                        "Contre": "⚔️",
                        "Cadeau de Noël": "🎄",    
                        "Malédiction": "📛",
                        "Calin": "🤗",    
                        "Envoûté": "👻",
                        "Garde du corps": "💂",
                        "Typhon": "🌪️",
                        "Bourdonnement": "🐝",
                        "Champignon": "🍄",
                        "Empoisonné": "☠️",
                        "blablabla": "💬",
                        "Piratage": "💻",
                        "Vol":"🦋",
                        "Malicieux": "🦝",
                        "Fatigue d'invocation": "😴",
                        "À main nue": "👊"}
                        
                        
        # Affichage du Terrain
        terrain_char = player_state['terrain']
        if terrain_char:
            # On s'assure que pv_max existe pour l'affichage
            pv_max = terrain_char.get('pv_max', terrain_char['pv'])
            terrain_desc = f"**{terrain_char['nom']}**\nPV: {terrain_char['pv']}/{pv_max} | ATQ: {terrain_char['attaque']}"
            
            # NOUVEAU : Affichage des statuts
            # NOUVEAU : Affichage des statuts
            if terrain_char.get("statuts"):                
                status_display = []
                for s in terrain_char["statuts"]:
                    if s == "Garde du corps":
                        # Afficher le nombre de gardes
                        nb_gardes = terrain_char.get("nb_gardes", 1)
                        status_display.append(f'{STATUS_EMOJIS.get(s, "❓")} {s} ({nb_gardes})')
                    else:
                        status_display.append(f'{STATUS_EMOJIS.get(s, "❓")} {s}')
                terrain_desc += f"\n*Statuts: {' '.join(status_display)}*"

            if "capacite" in terrain_char:
                capa = terrain_char['capacite']
                terrain_desc += f"\n**Capacité ({capa['cout']} PR):** {capa['nom']}\n*{capa['description']}*"
        else:
            terrain_desc = "Aucun personnage sur le terrain."
        embed.add_field(name="--- VOTRE TERRAIN ---", value=terrain_desc, inline=False)

        # Affichage de l'Inventaire
        for i, inv_char in enumerate(player_state['inventaire']):
            if inv_char:
                # On s'assure que pv_max existe pour l'affichage
                pv_max = inv_char.get('pv_max', inv_char['pv'])
                inv_desc = f"**{inv_char['nom']}**\nPV: {inv_char['pv']}/{pv_max} | ATQ: {inv_char['attaque']}"
                
                # NOUVEAU : Affichage des statuts
                # NOUVEAU : Affichage des statuts
                if inv_char.get("statuts"):                    
                    status_display = []
                    for s in inv_char["statuts"]:
                        if s == "Garde du corps":
                            # Afficher le nombre de gardes
                            nb_gardes = inv_char.get("nb_gardes", 1)
                            status_display.append(f'{STATUS_EMOJIS.get(s, "❓")} {s} ({nb_gardes})')
                        else:
                            status_display.append(f'{STATUS_EMOJIS.get(s, "❓")} {s}')
                    inv_desc += f"\n*Statuts: {' '.join(status_display)}*"

                if "capacite" in inv_char:
                    capa = inv_char['capacite']
                    inv_desc += f"\n**Capacité ({capa['cout']} PR):** {capa['nom']}"
                embed.add_field(name=f"Inventaire Slot {i+1}", value=inv_desc, inline=True)
            else:
                embed.add_field(name=f"Inventaire Slot {i+1}", value="Vide", inline=True)
        
        return embed

    async def update_player_dashboard(self, player_state, opponent_state, game_state, locked=False,show_opponent=True):
        """Met à jour le dashboard d'UN SEUL joueur en MP."""
        if player_state.get('is_ai'):            
            return # Si c'est l'IA, on n'envoie pas de MP. On arrête tout ici.
        
        if player_state.get('is_ready'):            
            locked = True
            
            
        member = player_state['member']
        embed = self._create_dashboard_embed(player_state, opponent_state,show_opponent )
        view = None if locked else PlayerDashboardView(self, player_state, game_state)
        
        try:
            dm_channel = member.dm_channel or await member.create_dm()
            if player_state['last_dm_id']:
                old_message = await dm_channel.fetch_message(player_state['last_dm_id'])
                await old_message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass # Le message n'existe plus, pas de problème
            
        new_message = await dm_channel.send(embed=embed, view=view)
        player_state['last_dm_id'] = new_message.id

    async def update_all_dashboards(self, game_state, locked=False):
        """Met à jour les dashboards des DEUX joueurs."""
        player_ids = list(game_state['players'].keys())
        p1_id, p2_id = player_ids[0], player_ids[1]
        
        p1_state = game_state['players'][p1_id]
        p2_state = game_state['players'][p2_id]
        
        show_opponent = game_state['phase'] == 'combat'
        # On met à jour les deux en parallèle
        await asyncio.gather(
            self.update_player_dashboard(p1_state, p2_state, game_state, locked,show_opponent ),
            self.update_player_dashboard(p2_state, p1_state, game_state, locked,show_opponent )
        )

# --- Vue pour la Sélection du Statut à Guérir ---
class StatusRemovalView(discord.ui.View):
    def __init__(self, target_char):
        super().__init__(timeout=180)
        self.chosen_status = None
        
        # Récupérer les statuts négatifs de la cible
        negative_statuses = []
        if "statuts" in target_char:
            for status in target_char["statuts"]:
                if status in ["Empoisonné", "Malédiction", "Envoûté"]:
                    negative_statuses.append(status)
        
        # S'il y a des statuts négatifs, créer un menu déroulant
        if negative_statuses:
            options = [discord.SelectOption(label=status, value=status) for status in negative_statuses]
            select = discord.ui.Select(placeholder="Choisissez un statut à guérir...", options=options)
            select.callback = self.select_callback
            self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        self.chosen_status = interaction.data['values'][0]
        self.stop()
        # Désactiver le menu pour montrer que le choix est fait
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Vous avez choisi de guérir le statut **{self.chosen_status}**.", view=self)
        
# --- NOUVELLE VUE : Sélection de Cible pour Piratage ---
class PiratageTargetView(discord.ui.View):
    def __init__(self, opponent_inventory):
        super().__init__(timeout=180) # 3 minutes pour choisir
        self.chosen_slot_index = None

        # Créer un bouton pour chaque personnage dans l'inventaire adverse
        for i, char in enumerate(opponent_inventory):
            if char:
                button = discord.ui.Button(
                    label=f"Supprimer {char['nom']}",
                    custom_id=f"pirate_{i}",
                    style=discord.ButtonStyle.danger
                )
                button.callback = self.button_callback
                self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        # Extraire l'index du custom_id
        slot_index = int(interaction.data['custom_id'].split('_')[1])
        self.chosen_slot_index = slot_index
        
        # Désactiver tous les boutons et confirmer le choix
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Cible du piratage verrouillée !", view=self)
        self.stop()
# Ne pas oublier la fonction setup à la fin du fichier
async def setup(bot: commands.Bot):
    await bot.add_cog(Game1v1ManagerCog(bot))