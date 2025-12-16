import discord
from discord import app_commands
from discord.ext import commands
import copy
import random
import math
import asyncio
import json
import os
import aiohttp

async def catalogue_personnage_autocompletion(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = [nom for nom in interaction.client.catalogue_personnages.keys()]
    return [app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()][:25]

class CombatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_combats_file = "active_combats.json"

    def _save_combat_state(self, channel_id, state):
        all_states = {}
        if os.path.exists(self.active_combats_file):
            with open(self.active_combats_file, 'r', encoding='utf-8') as f:
                try: all_states = json.load(f)
                except json.JSONDecodeError: pass
        all_states[str(channel_id)] = state
        with open(self.active_combats_file, 'w', encoding='utf-8') as f:
            json.dump(all_states, f, indent=4)

    def _load_all_combat_states(self):
        if not os.path.exists(self.active_combats_file): return {}
        with open(self.active_combats_file, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {}

    def _delete_combat_state(self, channel_id):
        all_states = self._load_all_combat_states()
        if str(channel_id) in all_states:
            del all_states[str(channel_id)]
            with open(self.active_combats_file, 'w', encoding='utf-8') as f:
                json.dump(all_states, f, indent=4)
                
    # AJOUTEZ CETTE MÉTHODE DANS cogs/combat.py, DANS LA CLASSE CombatCog

    @commands.Cog.listener()
    async def on_ready(self):
        """Se déclenche lorsque le bot est prêt. Reprend les combats interrompus."""
        print("CombatCog est prêt. Vérification des combats à reprendre...")
        
        # On attend un petit peu pour s'assurer que tous les cogs sont chargés
        await asyncio.sleep(5) 
        
        all_states = self._load_all_combat_states()
        
        if not all_states:
            print("Aucun combat actif à reprendre.")
            return

        resumed_count = 0
        for channel_id, state in all_states.items():
            try:
                print(f"Tentative de reprise du combat dans le salon {channel_id}...")
                # On relance le moteur de combat en lui passant l'état sauvegardé
                # asyncio.create_task permet de lancer plusieurs reprises en parallèle
                # sans bloquer le bot.
                asyncio.create_task(self.lancer_combat_engine(
                    log_message=None, # Le moteur le retrouvera lui-même
                    team_a=None,      # Idem
                    team_b=None,      # Idem
                    titre_combat=None,# Idem
                    nom_joueur=None,  # Idem
                    nom_adversaire=None, # Idem
                    resumed_state=state # C'est le paramètre le plus important
                ))
                resumed_count += 1
            except Exception as e:
                print(f"ERREUR lors de la reprise du combat pour le salon {channel_id}: {e}")
        
        if resumed_count > 0:
            print(f"✅ {resumed_count} combat(s) en cours de reprise.")


    def _creer_equipe_aleatoire(self) -> list:
        """Crée et retourne une équipe de 3 personnages aléatoires avec pouvoirs et équipements."""
        
        # Récupération des catalogues depuis le bot
        personnages_disponibles = list(self.bot.catalogue_personnages.values())
        pouvoirs_disponibles = list(self.bot.catalogue_de_pouvoirs.values())
        equipements_disponibles = list(self.bot.catalogue_equipements.values()) if hasattr(self.bot, 'catalogue_equipements') else []

        # Vérification qu'il y a assez de personnages
        if len(personnages_disponibles) < 3:
            # Dans un vrai cas, on pourrait lever une erreur, mais ici on retourne une liste vide
            # pour que la commande puisse l'indiquer à l'utilisateur.
            return []

        equipe = []
        personnages_choisis = random.sample(personnages_disponibles, 3)

        for perso_data in personnages_choisis:
            perso = copy.deepcopy(perso_data)
            
            # Attribution des pouvoirs (75% de chance par slot)
            perso["pouvoirs"] = [None, None, None]
            if pouvoirs_disponibles:
                for i in range(3):
                    if random.random() < 0.75:
                        pouvoir_choisi = random.choice(pouvoirs_disponibles)
                        perso["pouvoirs"][i] = copy.deepcopy(pouvoir_choisi)
            
            # Attribution d'un équipement (50% de chance)
            perso["equipement"] = None # S'assurer que la clé existe
            if equipements_disponibles and random.random() < 0.50:
                equipement_choisi = random.choice(equipements_disponibles)
                perso["equipement"] = copy.deepcopy(equipement_choisi)

            equipe.append(perso)
            
        return equipe

    async def lancer_combat_engine(self, log_message: discord.Message, team_a: list, team_b: list, titre_combat: str, nom_joueur: str, nom_adversaire: str, resumed_state: dict = None, is_pve: bool = False):
        # ===================================================================
        # ===================  INITIALISATION STRUCTURÉE  ===================
        # ===================================================================

        # --- ÉTAPE 1: DÉCLARATION DE TOUTES LES VARIABLES ---
        # Elles existeront toujours, avec une valeur par défaut.
        
        embed = None
        
        team_a_last_power, team_b_last_power = None, None
        team_a_poulets, team_b_poulets = 0, 0
        team_a_talon_active, team_b_talon_active = False, False
        team_a_is_stunned, team_b_is_stunned = False, False
        team_a_peur_bleu, team_b_peur_bleu = False, False
        prescience_timer_a, prescience_timer_b = None, None
        prescience_damage_multiplier_a, prescience_damage_multiplier_b = 0, 0
        prescience_caster_a, prescience_caster_b = 0, 0
        team_a_bouclier_magique, team_b_bouclier_magique = False, False
        bouclier_magique_expire_a, bouclier_magique_expire_b = 0, 0
        team_a_bombardement_stun, team_b_bombardement_stun = False, False
        zombie_a, zombie_b = None, None
        active_a, active_b = None, None
        turn_a, tour_count, combat_log = True, 0, []
        tempo_pending_a, tempo_pending_b = False, False
        is_bonus_turn_a, is_bonus_turn_b = False, False
        grimoire_bonus_a, grimoire_bonus_b = 0, 0
        catalyseur_bonus_a, catalyseur_bonus_b = 0.0, 0.0
        
        def recalculate_and_update_attack(character):                    
            """Recalcule l'attaque d'un personnage en fonction de sa base et de ses effets."""                    
            bonus_attaque = sum(e['value'] for e in character.get('effects', []) if e['type'] == 'attack_buff')                    
            character['attaque'] = character['base_attaque'] + bonus_attaque

        # --- ÉTAPE 2: GESTION DES DEUX CAS (NOUVEAU VS REPRIS) ---
        if resumed_state:
            # CAS 1 : On reprend un combat depuis une sauvegarde
            try:
                nom_joueur = resumed_state.get('nom_joueur', 'Joueur')
                team_a = resumed_state['team_a']
                team_b = resumed_state['team_b']
                titre_combat = resumed_state['titre_combat']
                nom_adversaire = resumed_state['nom_adversaire']
                active_a = next((p for p in team_a if p['nom'] == resumed_state['active_a_nom']), None)
                active_b = next((p for p in team_b if p['nom'] == resumed_state['active_b_nom']), None)

                # Chargement sécurisé des variables de combat
                combat_vars = resumed_state.get('variables', {})
                team_a_last_power = combat_vars.get('team_a_last_power')
                team_b_last_power = combat_vars.get('team_b_last_power')
                team_a_poulets = combat_vars.get('team_a_poulets', 0)
                team_b_poulets = combat_vars.get('team_b_poulets', 0)
                team_a_talon_active = combat_vars.get('team_a_talon_active', False)
                team_b_talon_active = combat_vars.get('team_b_talon_active', False)
                team_a_is_stunned = combat_vars.get('team_a_is_stunned', False)
                team_b_is_stunned = combat_vars.get('team_b_is_stunned', False)
                team_a_peur_bleu = combat_vars.get('team_a_peur_bleu', False)
                team_b_peur_bleu = combat_vars.get('team_b_peur_bleu', False)
                prescience_timer_a = combat_vars.get('prescience_timer_a')
                prescience_timer_b = combat_vars.get('prescience_timer_b')
                prescience_damage_multiplier_a = combat_vars.get('prescience_damage_multiplier_a', 0)
                prescience_damage_multiplier_b = combat_vars.get('prescience_damage_multiplier_b', 0)
                prescience_caster_a = combat_vars.get('prescience_caster_a', 0)
                prescience_caster_b = combat_vars.get('prescience_caster_b', 0)
                team_a_bouclier_magique = combat_vars.get('team_a_bouclier_magique', False)
                team_b_bouclier_magique = combat_vars.get('team_b_bouclier_magique', False)
                bouclier_magique_expire_a = combat_vars.get('bouclier_magique_expire_a', 0)
                bouclier_magique_expire_b = combat_vars.get('bouclier_magique_expire_b', 0)
                team_a_bombardement_stun = combat_vars.get('team_a_bombardement_stun', False)
                team_b_bombardement_stun = combat_vars.get('team_b_bombardement_stun', False)
                zombie_a = combat_vars.get('zombie_a')
                zombie_b = combat_vars.get('zombie_b')
                turn_a = combat_vars.get('turn_a', True)
                tour_count = combat_vars.get('tour_count', 0)
                combat_log = combat_vars.get('combat_log', [])
                tempo_pending_a = combat_vars.get('tempo_pending_a', False)
                tempo_pending_b = combat_vars.get('tempo_pending_b', False)
                is_bonus_turn_a = combat_vars.get('is_bonus_turn_a', False)
                is_bonus_turn_b = combat_vars.get('is_bonus_turn_b', False)

                # Récupération du message Discord existant (correction cruciale)
                channel = await self.bot.fetch_channel(resumed_state['channel_id'])
                log_message = await channel.fetch_message(resumed_state['message_id'])
                await channel.send("🤖 Le combat reprend suite à un redémarrage.", delete_after=10)
            
            except (discord.NotFound, discord.Forbidden, KeyError) as e:
                print(f"Erreur critique lors de la reprise du combat {resumed_state.get('channel_id')}: {e}")
                self._delete_combat_state(resumed_state.get('channel_id'))
                return
        else:

            active_a, active_b = team_a[0], team_b[0]
            
            # Initialisation des personnages (une seule fois)
            # ... la suite du code ...
            
            # Initialisation des personnages (une seule fois)
            for p in team_a + team_b:
                p['max_pv'] = p['pv']
                p['base_attaque'] = p['attaque']
                p['effects'] = []
                p['poison_stacks'] = 0
                p['etats'] = []
                p['bonus_degats'] = 0
                p['couronne_active'] = False
                p['bandeau_used_this_stint'] = False
                p['pv_at_turn_end'] = p['pv']
                if p.get('nom') == "Le Parieur": p['parieur_ability_ready'] = True
                if 'armure' not in p: p['armure'] = 0
                if p.get('nom') == "La Samourai": p['armure'] = 0
                if p.get('nom') == "La Nécromancienne": p['a_ressuscite'] = False
                if p.get('nom') == "Le Robot":
                    p['repair_mode_active'] = False
                    p['repair_turns_left'] = 0
                    p['ability_used_this_stint'] = False
                if p.get('nom') == "Robot mage":                        
                    p['bonus_degats'] = 3 # Bonus initial                    
                else:                        
                    p['bonus_degats'] = 0
                if p.get("pouvoirs"):
                    for pouvoir in p["pouvoirs"]:
                        if pouvoir and pouvoir.get('nom') == "Chaos":
                            pouvoir['activation'] = '??'
                if "equipement" not in p: p["equipement"] = None # S'assurer que la clé existe
                if p.get("equipement"):
                    

                    if p["equipement"].get("nom") == "Tempo":
                        p['armure'] += 2
                    if p["equipement"].get("nom") == "Grimoire interdit":            
                        p['max_pv'] = math.ceil(p['max_pv'] * 0.25)  # Réduire à 25% des PV max
                        p['pv'] = p['max_pv'] # On met les PV actuels au nouveau max                        
                        p['grimoire_turns_left'] = 0 # Initialise le compteur                        
                        # Sauvegarde les pouvoirs originaux pour pouvoir les restaurer                        
                        p['original_pouvoirs'] = copy.deepcopy(p.get('pouvoirs'))
                    if p["equipement"].get("nom") == "Hachoir":                        
                        p['base_attaque'] += 3                        
                        recalculate_and_update_attack(p) # On met à jour l'attaque immédiatement
                    if p["equipement"].get("nom") == "Lance-bouclier":                        
                        p['base_attaque'] += 5                        
                        p['max_pv'] += 5                        
                        p['pv'] += 5 # Important pour que le perso commence avec tous ses PV                        
                        recalculate_and_update_attack(p)
                    if p["equipement"].get("nom") == "Cape magique":                        
                        p['cape_magique_charges'] = 10 # Initialise le compteur de charges
                    

                      
            

        # --- ÉTAPE 3: SETUP COMMUN (CRÉATION DES OUTILS) ---
        # Ces éléments sont nécessaires dans les deux cas.
        embed = discord.Embed(title=f"⚔️ {titre_combat} en cours... ⚔️", color=discord.Color.red())

           

        def update_embed_fields():
            nonlocal team_a_poulets, team_b_poulets, team_a_bouclier_magique, team_b_bouclier_magique, zombie_a, zombie_b
            embed.clear_fields()
            stats_a = f"**PV :** {active_a['pv']}/{active_a['max_pv']}\n**Attaque :** {active_a['attaque']}"
            if active_a.get('bonus_degats', 0) > 0:                
                stats_a += f" (+{active_a['bonus_degats']})"
            if active_a.get("equipement"):        
                stats_a += f"\n**Équipement :** {active_a['equipement']['nom']}"
                if 'durability' in active_a['equipement']: # <--- AJOUT                    
                    stats_a += f" (Dur: {active_a['equipement']['durability']})"
            if active_a.get('armure', 0) > 0: stats_a += f"\n**Armure :** {active_a.get('armure', 0)}"
            if active_a.get('etats'):                
                for etat in active_a['etats']:                    
                    if etat == 'coup_critique':                        
                        stats_a += f"\n**Statut :** 💥 Coup Critique"
                    if etat == 'chanceux':                     
                        stats_a += f"\n**Statut :** 🍀 Chanceux"
                    if etat == 'affaibli':                        
                        stats_a += f"\n**Statut :** 🩸 Affaibli"
                    if etat == 'malade':                        
                        stats_a += f"\n**Statut :** 🤒 Malade"
                    if etat == 'malchanceux':                        
                        stats_a += f"\n**Statut :** 💩 Malchanceux"
                    if etat == 'bandeau_invincible':                        
                        stats_a += f"\n**Statut :** 🎗️ Détermination"
            if active_a.get('poison_stacks', 0) > 0: stats_a += f"\n**Statut :** ☠️ Empoisonné (x{active_a['poison_stacks']})"
            for effect in active_a.get('effects', []):
                if effect['type'] == 'attack_buff':
                    stats_a += f"\n**Statut :** 💪 {effect['name']} (+{effect['value']} ATQ / {effect['duration']}t)"
            if active_a.get('repair_mode_active', False): stats_a += f"\n**Statut :** 🔧 En réparation ({active_a.get('repair_turns_left', 0)} tours)"
            if active_a.get("equipement") and active_a["equipement"].get("nom") == "Cape magique" and active_a.get('cape_magique_charges', 0) > 0:                
                stats_a += f"\n**Statut :** 🧥 Cape Magique ({active_a['cape_magique_charges']} charges)"
            if team_a_bouclier_magique: stats_a += f"\n**Statut :** 🛡️ Bouclier Magique"
            if team_a_talon_active: stats_a += f"\n**Statut :** 🎯 Talon d'Achille actif"
            stats_a += f"\n**Capacité :** *{active_a['capacite_unique']}*"
            pouvoirs_a_str = "\n**Pouvoirs :**"
            for p in active_a.get("pouvoirs", [None, None, None]):
                if p:
                    display_chance = ""
                    if p['nom'] == "Chaos": display_chance = f"{p['activation']}%" if isinstance(p['activation'], int) else "??%"
                    else:
                        activation_chance = p['activation']
                        if p['nom'] == "Pile ou Face" and active_a['nom'] == "Le Parieur": activation_chance = 50
                        elif p['nom'] == "Armure" and active_a['nom'] == "La Samourai": activation_chance = 50
                        elif p['nom'] == "Batteries d'urgences" and active_a['nom'] == "Le Robot": activation_chance = 50
                        elif p['nom'] == "Nécromancie" and active_a['nom'] == "La Nécromancienne": activation_chance = 50
                        elif p['nom'] == "Bénédiction" and active_a['nom'] == "La Qilin": activation_chance = 50
                        display_chance = f"{activation_chance}%"
                    if active_a.get("equipement") and active_a["equipement"].get("nom") == "Grimoire interdit":                        
                        if active_a.get('grimoire_turns_left', 0) > 0:                            
                            display_chance = "100% 📖" # On ajoute un emoji pour que ce soit clair
                    pouvoirs_a_str += f"\n> {p['nom']} ({display_chance})"
                    if 'durability' in p: # <--- AJOUT                        
                        pouvoirs_a_str += f" (Dur: {p['durability']})" # <--- AJOUT
                else: pouvoirs_a_str += "\n> Vide"
            stats_a += pouvoirs_a_str
            if zombie_a: stats_a += f"\n\n🧟 **Zombie**\n**PV :** {zombie_a['pv']}/{zombie_a['max_pv']} | **Attaque :** {zombie_a['attaque']}"
            dead_a_names = [p['nom'] for p in team_a if p['pv'] <= 0]
            if dead_a_names: stats_a += f"\n\n💀 **KO:** {', '.join(dead_a_names)}"
            if team_a_poulets > 0: stats_a += f"\n🐔 **Poulets : {team_a_poulets}**"
            if prescience_timer_b is not None: stats_a += f"\n⏳ **Prescience actif** : {prescience_timer_b} tours restants"
            embed.add_field(name=f"{nom_joueur} : {active_a['nom']}", value=stats_a, inline=True)

            stats_b = f"**PV :** {active_b['pv']}/{active_b['max_pv']}\n**Attaque :** {active_b['attaque']}"
            if active_b.get('bonus_degats', 0) > 0:                
                stats_b += f" (+{active_b['bonus_degats']})"
            if active_b.get("equipement"):        
                stats_b += f"\n**Équipement :** {active_b['equipement']['nom']}"
                if 'durability' in active_b['equipement']: # <--- AJOUT                    
                    stats_b += f" (Dur: {active_b['equipement']['durability']})"
            if active_b.get('armure', 0) > 0: stats_b += f"\n**Armure :** {active_b.get('armure', 0)}"
            if active_b.get('etats'):                
                for etat in active_b['etats']:                    
                    if etat == 'coup_critique':                        
                        stats_b += f"\n**Statut :** 💥 Coup Critique"
                    if etat == 'chanceux':                     
                        stats_b += f"\n**Statut :** 🍀 Chanceux"
                    if etat == 'affaibli':                        
                        stats_b += f"\n**Statut :** 🩸 Affaibli"
                    if etat == 'malade':                        
                        stats_b += f"\n**Statut :** 🤒 Malade"
                    if etat == 'malchanceux':                        
                        stats_b += f"\n**Statut :** 💩 Malchanceux"
                    if etat == 'bandeau_invincible':                        
                        stats_b += f"\n**Statut :** 🎗️ Détermination"
            if active_b.get('poison_stacks', 0) > 0: stats_b += f"\n**Statut :** ☠️ Empoisonné (x{active_b['poison_stacks']})"
            for effect in active_b.get('effects', []):
                if effect['type'] == 'attack_buff':
                    stats_b += f"\n**Statut :** 💪 {effect['name']} (+{effect['value']} ATQ / {effect['duration']}t)"
            if active_b.get('repair_mode_active', False): stats_b += f"\n**Statut :** 🔧 En réparation ({active_b.get('repair_turns_left', 0)} tours)"
            if active_b.get("equipement") and active_b["equipement"].get("nom") == "Cape magique" and active_b.get('cape_magique_charges', 0) > 0:                
                stats_b += f"\n**Statut :** 🧥 Cape Magique ({active_b['cape_magique_charges']} charges)"
            if team_b_bouclier_magique: stats_b += f"\n**Statut :** 🛡️ Bouclier Magique"
            if team_b_talon_active: stats_b += f"\n**Statut :** 🎯 Talon d'Achille actif"
            stats_b += f"\n**Capacité :** *{active_b['capacite_unique']}*"
            pouvoirs_b_str = "\n**Pouvoirs :**"
            if is_pve:                
                pouvoirs_b_str += "\n> ???"                
                pouvoirs_b_str += "\n> ???"                
                pouvoirs_b_str += "\n> ???"            
            else:
                for p in active_b.get("pouvoirs", [None, None, None]):
                    if p:
                        display_chance = ""
                        if p['nom'] == "Chaos": display_chance = f"{p['activation']}%" if isinstance(p['activation'], int) else "??%"
                        else:
                            activation_chance = p['activation']
                            if p['nom'] == "Pile ou Face" and active_b['nom'] == "Le Parieur": activation_chance = 50
                            elif p['nom'] == "Armure" and active_b['nom'] == "La Samourai": activation_chance = 50
                            elif p['nom'] == "Batteries d'urgences" and active_b['nom'] == "Le Robot": activation_chance = 50
                            elif p['nom'] == "Nécromancie" and active_b['nom'] == "La Nécromancienne": activation_chance = 50
                            elif p['nom'] == "Bénédiction" and active_b['nom'] == "La Qilin": activation_chance = 50
                            display_chance = f"{activation_chance}%"
                        if active_b.get("equipement") and active_b["equipement"].get("nom") == "Grimoire interdit":                        
                            if active_b.get('grimoire_turns_left', 0) > 0:                            
                                display_chance = "100% 📖" # On ajoute un emoji pour que ce soit clair
                        pouvoirs_b_str += f"\n> {p['nom']} ({display_chance})"
                        if 'durability' in p: # <--- AJOUT                        
                            pouvoirs_b_str += f" (Dur: {p['durability']})" # <--- AJOUT
                    else: pouvoirs_b_str += "\n> Vide"
            stats_b += pouvoirs_b_str
            if zombie_b: stats_b += f"\n\n🧟 **Zombie**\n**PV :** {zombie_b['pv']}/{zombie_b['max_pv']} | **Attaque :** {zombie_b['attaque']}"
            dead_b_names = [p['nom'] for p in team_b if p['pv'] <= 0]
            if dead_b_names: stats_b += f"\n\n💀 **KO:** {', '.join(dead_b_names)}"
            if team_b_poulets > 0: stats_b += f"\n🐔 **Poulets : {team_b_poulets}**"
            if prescience_timer_a is not None: stats_b += f"\n⏳ **Prescience actif** : {prescience_timer_a} tours restants"
            embed.add_field(name=f"{nom_adversaire} : {active_b['nom']}", value=stats_b, inline=True)
        

        # --- NOUVELLE FONCTION POUR GÉRER LE KARMA ---
        async def set_luck_state(character, new_state):
            """Applique un état de chance ('chanceux' ou 'malchanceux') et retire l'état opposé."""
            etats = character.get('etats', [])
            
            # On retire les deux pour être sûr, peu importe l'ordre
            if 'chanceux' in etats:
                etats.remove('chanceux')
            if 'malchanceux' in etats:
                etats.remove('malchanceux')
            
            # On ajoute le nouvel état s'il y en a un
            if new_state == 'chanceux':
                etats.append('chanceux')
                await add_action_to_log(f"⚖️ Le karma bascule ! **{character['nom']}** est maintenant **Chanceux**.", delay=0)
            elif new_state == 'malchanceux':
                etats.append('malchanceux')
                await add_action_to_log(f"⚖️ Le karma bascule ! **{character['nom']}** est maintenant **Malchanceux**.", delay=0)
        # --- FIN DE LA FONCTION KARMA ---


        async def apply_grimoire_buff(character):
            if character.get("equipement") and character["equipement"].get("nom") == "Grimoire interdit":
                character['grimoire_turns_left'] = 3
                await add_action_to_log(f"📖 Le Grimoire interdit de **{character['nom']}** s'active ! Ses pouvoirs sont à 100% pour 3 tours.", delay=0.5)

        async def remove_grimoire_buff(character):
            if character.get("equipement") and character["equipement"].get("nom") == "Grimoire interdit":
                if character.get('grimoire_turns_left', 0) > 0:
                    character['grimoire_turns_left'] = 0
                    # Restaure les pourcentages d'origine
                    character['pouvoirs'] = copy.deepcopy(character.get('original_pouvoirs'))
                    await add_action_to_log(f"📕 Le pouvoir du Grimoire de **{character['nom']}** se dissipe.", delay=0.5)
        
                


               

        async def apply_baguette_buff(character):
            if character.get("equipement") and character["equipement"].get("nom") == "Baguette explosive":
                if 'coup_critique' not in character.get('etats', []):
                    character['etats'].append('coup_critique')
                await set_luck_state(character, 'chanceux')
                await add_action_to_log(f"🪄 La Baguette explosive de **{character['nom']}** crépite d'énergie ! Il gagne les statuts **Coup Critique** et **Chanceux**.", delay=0.5)

        async def remove_baguette_buff(character):
            # On retire les statuts uniquement s'ils sont présents pour éviter les erreurs
            removed_something = False
            if 'coup_critique' in character.get('etats', []):
                character['etats'].remove('coup_critique')
                removed_something = True
            if 'chanceux' in character.get('etats', []):
                character['etats'].remove('chanceux')
                removed_something = True
            
            # On affiche le message seulement si un statut a bien été retiré
            if removed_something:
                 await add_action_to_log(f"✨ L'énergie de la Baguette explosive de **{character['nom']}** se dissipe.", delay=0.5)

        # ... la suite de votre code (roll_dice, etc.)

        def roll_dice(character, min_val, max_val, mode='higher'):
            """
            Effectue un jet de dé. Si le personnage est 'chanceux',
            le jet est effectué deux fois et le meilleur résultat est retourné.
            mode 'higher': le plus grand est le meilleur (dégâts, % chaos).
            mode 'lower': le plus petit est le meilleur (% activation pouvoir).
            """
            is_lucky = 'chanceux' in character.get('etats', [])
            is_unlucky = 'malchanceux' in character.get('etats', [])
            
            if not is_lucky and not is_unlucky:
                roll = random.randint(min_val, max_val)                
                return (roll, None) # On retourne le jet et None
            else:
                roll1 = random.randint(min_val, max_val)
                roll2 = random.randint(min_val, max_val)
                
                if is_lucky:
                    if mode == 'higher':
                        return (max(roll1, roll2), min(roll1, roll2))
                    else: # mode == 'lower'
                        return (min(roll1, roll2), max(roll1, roll2))
                else: # is_unlucky                    
                    if mode == 'higher':                        
                        return (min(roll1, roll2), max(roll1, roll2)) # Le pire est le plus petit                    
                    else: # mode == 'lower'                        
                        return (max(roll1, roll2), min(roll1, roll2)) # Le pire est le plus grand
                # ... juste après la fonction roll_dice modifiée ...

        async def async_roll_for_damage(character, min_val, max_val):
            """Enveloppe pour les jets de dégâts qui gère l'affichage du statut Chanceux."""
            chosen_roll, other_roll = roll_dice(character, min_val, max_val, mode='higher')
            
            if 'chanceux' in character.get('etats', []) and other_roll is not None and (chosen_roll - other_roll >= 5):                
                await add_action_to_log(f"🍀 La chance sourit à **{character['nom']}** ! (Jet : {chosen_roll} au lieu de {other_roll})", delay=0.5)
            elif 'malchanceux' in character.get('etats', []) and other_roll is not None and (other_roll - chosen_roll >= 5):                
                await add_action_to_log(f"💩 La malchance frappe **{character['nom']}** ! (Jet : {chosen_roll} au lieu de {other_roll})", delay=0.5)
            
            return chosen_roll

        async def async_roll_for_activation(character, activation_chance):
            """Enveloppe pour les jets d'activation qui gère l'affichage du statut Chanceux."""
            chosen_roll, other_roll = roll_dice(character, 1, 100, mode='lower')

            # La condition est : le moins bon jet aurait échoué ET le meilleur jet réussit.
            if 'chanceux' in character.get('etats', []) and other_roll is not None and (other_roll > activation_chance and chosen_roll <= activation_chance):                 
                await add_action_to_log(f"🍀 La chance sourit à **{character['nom']}** et active son pouvoir ! (Jet : {chosen_roll} au lieu de {other_roll})", delay=0.5)
            # La condition est : le bon jet aurait réussi ET le mauvais jet (celui qui est choisi) a échoué.            
            elif 'malchanceux' in character.get('etats', []) and other_roll is not None and (other_roll <= activation_chance and chosen_roll > activation_chance):                 
                await add_action_to_log(f"💩 La malchance frappe **{character['nom']}** et empêche son pouvoir de s'activer ! (Jet : {chosen_roll} au lieu de {other_roll})", delay=0.5)

            return chosen_roll <= activation_chance # Renvoie True si le pouvoir s'active, False sinon


        async def add_action_to_log(action_text, delay=1.0):
            await asyncio.sleep(delay)
            # On ajoute la nouvelle action au log du tour actuel
            combat_log[-1] += f"\n{action_text}"

            # --- NOUVELLE LOGIQUE POUR CONSTRUIRE LA DESCRIPTION SANS CRASH ---
            display_log_lines = []
            current_length = 0
            char_limit = 4000 # On se garde une petite marge de sécurité par rapport à 4096

            # On parcourt le log complet à l'envers pour prioriser les actions les plus récentes
            for entry in reversed(combat_log):
                # On ajoute 1 pour le caractère de nouvelle ligne "\n" qui sera ajouté plus tard
                if current_length + len(entry) + 1 > char_limit:
                    break # On arrête si l'ajout du prochain tour nous fait dépasser la limite
                
                # On insère l'entrée au début de notre liste d'affichage pour garder l'ordre chronologique
                display_log_lines.insert(0, entry)
                current_length += len(entry) + 1
            
            # On construit la description finale
            embed.description = "\n".join(display_log_lines)
            # --- FIN DE LA NOUVELLE LOGIQUE ---

            try:
                await log_message.edit(embed=embed)
            except discord.errors.HTTPException as e:
                print(f"Erreur lors de l'édition du message (log trop long ?) : {e}")
                # En cas d'erreur, on peut tenter d'envoyer une version encore plus courte
                embed.description = display_log_lines[-1] # On affiche seulement le tour actuel
                await log_message.edit(embed=embed)

        
        
                
        def calculate_final_damage(base_damage, attaquant):
            """Calcule les dégâts finaux en appliquant les effets comme le coup critique."""
            final_damage = base_damage + attaquant.get('bonus_degats', 0)
            did_crit = False
            
            if 'coup_critique' in attaquant.get('etats', []) and random.random() < 0.50:
                # 50% de chance de coup critique
                crit_bonus = math.ceil(final_damage * 1.5) # Augmentation de 150%
                final_damage = crit_bonus
                did_crit = True
                
            return final_damage, did_crit

        async def activate_copied_power(copied_power, attaquant, defenseur, turn_a, nom_attaquant, nom_defenseur ):
            if not copied_power:        
                await add_action_to_log("Aucun pouvoir n'a été copié. Mimétisme échoue.")        
                return
            nonlocal team_a_talon_active, team_b_talon_active, team_a_poulets, team_b_poulets, prescience_timer_a, prescience_timer_b, prescience_damage_multiplier_a, prescience_damage_multiplier_b, prescience_caster_a, prescience_caster_b, team_a_bombardement_stun, team_b_bombardement_stun, team_a_is_stunned, team_b_is_stunned, team_a_peur_bleu, team_b_peur_bleu, zombie_a, zombie_b, team_a_bouclier_magique, team_b_bouclier_magique, bouclier_magique_expire_a, bouclier_magique_expire_b, tour_count, active_a, active_b, nom_adversaire, damage_multiplier

            bonus_attaque_copie = sum(e['value'] for e in attaquant['effects'] if e['type'] == 'attack_buff')
            attaque_effective_copie = attaquant['base_attaque'] + bonus_attaque_copie
            team_attaquant = team_a if turn_a else team_b
            team_defenseur = team_b if turn_a else team_a

            if copied_power == "Frénésie":
                await add_action_to_log(f"🔥 {attaquant['nom']} active **Frénésie** !")
                base_extra_damage = 0                                            
                if attaquant.get('couronne_active', False):                                                
                    await add_action_to_log(f"👑 La Frénésie du survivant est **brute** et prévisible !")                                                
                    base_extra_damage = attaque_effective_copie * damage_multiplier                                            
                else:                                                
                    base_extra_damage = await async_roll_for_damage(attaquant, 1, attaque_effective_copie) * damage_multiplier
                extra_damage, did_crit = calculate_final_damage(base_extra_damage, attaquant)    
                if did_crit:        
                    await add_action_to_log("💥 **COUP CRITIQUE !**")    
                await apply_damage(defenseur['nom'], defenseur, nom_attaquant, attaquant ,extra_damage, add_action_to_log, turn_a)
            elif copied_power == "Don":
                allies_blesses = [p for p in team_attaquant if p != attaquant and p['pv'] > 0 and p['pv'] < p['max_pv']]
                if allies_blesses:
                    cible_soin = min(allies_blesses, key=lambda p: p['pv'])
                    soin = math.ceil(attaquant['max_pv'] * 0.25)                                                
                    await add_action_to_log(f"🎁 {nom_attaquant} active **Don** !")                                                
                    await apply_heal(cible_soin, soin, "Don")
            elif copied_power == "Le Poulet":
                await add_action_to_log(f"🐔 {attaquant['nom']} invoque un poulet protecteur !")
                if turn_a: team_a_poulets += 1
                else: team_b_poulets += 1
            elif copied_power == "Bourbier":
                await add_action_to_log(f"🌪️ {attaquant['nom']} active **Bourbier** et empêche {defenseur['nom']} de jouer son prochain tour !")
                if turn_a: team_b_is_stunned = True
                else: team_a_is_stunned = True
            elif copied_power == "Prescience":
                if turn_a:
                    if prescience_timer_b is not None: prescience_damage_multiplier_b += 1
                    else:
                        prescience_timer_b = 10
                        prescience_caster_b = attaquant
                else:
                    if prescience_timer_a is not None: prescience_damage_multiplier_a += 1
                    else:
                        prescience_timer_a = 10
                        prescience_caster_a = attaquant
                await add_action_to_log(f"🔮 {attaquant['nom']} active ou renforce **Prescience** !")
            elif copied_power == "Peur bleu":
                await add_action_to_log(f"😨 {attaquant['nom']} active **Peur bleu** ! {defenseur['nom']} ne pourra pas changer de personnage.")
                if turn_a: team_b_peur_bleu = True
                else: team_a_peur_bleu = True
            elif copied_power == "Rugissement primal":
                personnages_banc_vivants = [p for p in team_defenseur if p['pv'] > 0 and p != defenseur]
                if personnages_banc_vivants:
                    ancien_defenseur = defenseur
                    await handle_character_swap_out(ancien_defenseur)
                    nouveau_defenseur = random.choice(personnages_banc_vivants)
                    await add_action_to_log(f"🗣️ {attaquant['nom']} lance **Rugissement primal** ! {defenseur['nom']} est remplacé par **{nouveau_defenseur['nom']}** !")
                    if turn_a: active_b = nouveau_defenseur
                    else: active_a = nouveau_defenseur
                    defenseur = nouveau_defenseur
                    nom_defenseur = f"{nom_adversaire} **{defenseur['nom']}**" if turn_a else f"**{defenseur['nom']}**"
                    await handle_character_swap_in(nouveau_defenseur, attaquant)
                else:
                    await add_action_to_log(f"🗣️ {attaquant['nom']} lance **Rugissement primal**, mais il n'y a personne sur le banc !")
            elif copied_power == "Bouclier magique":
                if attaquant.get("equipement") and attaquant["equipement"].get("nom") == "Cape magique" and attaquant.get('cape_magique_charges', 0) > 0:                                                
                    await add_action_to_log(f"✨ {nom_attaquant} canalise l'énergie de sa **Cape magique** dans une attaque !")                                                
                    # On copie/colle la logique d'une attaque de base (comme pour Frénésie)                                                
                    base_extra_damage = await async_roll_for_damage(attaquant, 1, attaque_effective_copie) * damage_multiplier                                                
                    extra_damage, did_crit = calculate_final_damage(base_extra_damage, attaquant)                                                    
                    if did_crit:                                                            
                        await add_action_to_log("💥 **COUP CRITIQUE !**")                                                
                    await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant ,extra_damage, add_action_to_log, turn_a)
                else:
                    await add_action_to_log(f"🛡️ {attaquant['nom']} active **Bouclier magique** !")
                    if turn_a:
                        team_a_bouclier_magique = True
                        bouclier_magique_expire_a = tour_count + 2
                    else:
                        team_b_bouclier_magique = True
                        bouclier_magique_expire_b = tour_count + 2
            elif copied_power == "Combo":
                # Pour une copie, on considère que c'est le premier pouvoir activé
                multiplicateur = [0.25, 0.75, 1.50][min(pouvoirs_actives_ce_tour, 2)]
                base_combo_damage = math.ceil(attaque_effective_copie * multiplicateur) * damage_multiplier    
                damage, did_crit = calculate_final_damage(base_combo_damage, attaquant)    
                await add_action_to_log(f"💥 {attaquant['nom']} active **Combo** (dégâts de base: **{base_combo_damage}**) !")    
                if did_crit:        
                    await add_action_to_log("💥 **COUP CRITIQUE !**")    
                await apply_damage(defenseur['nom'], defenseur, nom_attaquant, attaquant ,damage, add_action_to_log, turn_a)
            elif copied_power == "Bombardement":
                await add_action_to_log(f"✈️ {attaquant['nom']} lance un **Bombardement** !")
                if turn_a: team_a_bombardement_stun = True
                else: team_b_bombardement_stun = True
                cibles_reserve = [p for p in team_defenseur if p['pv'] > 0 and p != defenseur]
                if cibles_reserve:
                    base_bomb_damage = math.ceil(attaque_effective_copie * 0.5) * damage_multiplier        
                    for cible in cibles_reserve:            
                        damage, did_crit = calculate_final_damage(base_bomb_damage, attaquant)            
                        crit_msg = " (💥 **Critique !**)" if did_crit else ""            
                        cible['pv'] = max(0, cible['pv'] - damage)            
                        await add_action_to_log(f"💥 **{cible['nom']}** subit **{damage}** pts de dégâts{crit_msg} !")
                else:
                    await add_action_to_log("...mais la réserve adverse est vide !")
            elif copied_power == "Pile ou Face":
                await add_action_to_log(f"🎲 {attaquant['nom']} utilise **Pile ou Face** !")
                if random.choice(['pile', 'face']) == 'face':
                    base_damage, did_crit = calculate_final_damage(attaque_effective_copie, attaquant) 
                    damage = base_damage * damage_multiplier  
                    await add_action_to_log(f"🤑 **FACE !** (dégâts de base: **{attaque_effective_copie}**)")        
                    if did_crit:            
                        await add_action_to_log("💥 **COUP CRITIQUE !**")
                    await apply_damage(defenseur['nom'], defenseur, nom_attaquant, attaquant ,damage, add_action_to_log, turn_a)
                else:
                    damage = attaque_effective_copie                                               
                    await add_action_to_log(f"😵 **PILE !** Il subit **{damage}** pts de dégâts bruts.")                                                                                                
                    # On applique les dégâts à soi-même et on récupère les dégâts réellement subis                                                
                    damage_taken = await apply_damage(nom_attaquant, attaquant, "Lui-même", attaquant, damage, add_action_to_log, not turn_a)                                                
                    # On vérifie si la synergie s'active                                                
                    if damage_taken > 0 and attaquant.get("equipement") and attaquant["equipement"].get("nom") == "Côte épineuse":                                                    
                        reflected_damage = math.ceil(damage_taken * 0.5) * damage_multiplier                                                   
                        await add_action_to_log(f"💡 La malchance de {nom_attaquant} se retourne contre son adversaire !", delay=0.5)                                                    
                        await add_action_to_log(f"🌵 La Côte épineuse renvoie **{reflected_damage}** pts de dégâts à {nom_defenseur} !", delay=0.5)                                                                                                        
                        # On applique les dégâts de renvoi à l'adversaire (le vrai défenseur)                                                    
                        defenseur['pv'] -= reflected_damage                                                    
                        await add_action_to_log(f"🩸 {nom_defenseur} subit les dégâts. (PV restants : {max(0, defenseur['pv'])})")
            elif copied_power == "Armure":
                await add_action_to_log(f"🛡️ {attaquant['nom']} active **Armure** !")
                attaquant['armure'] += 3
            elif copied_power == "Batteries d'urgences":
                await add_action_to_log(f"🔋 {attaquant['nom']} active **Batteries d'urgences** !")
                soin = math.ceil(attaquant['max_pv'] * 0.25)
                await apply_heal(attaquant, soin, "Batteries d'urgences")   
            elif copied_power == "Nécromancie":
                zombie_actuel = zombie_a if turn_a else zombie_b
                if not zombie_actuel:
                    await add_action_to_log(f"💀 {attaquant['nom']} active **Nécromancie** !")
                    zombie_pv = math.ceil(attaquant['max_pv'] * 0.33)
                    zombie_atk = attaquant['attaque']
                    nouveau_zombie = {'pv': zombie_pv, 'max_pv': zombie_pv, 'attaque': zombie_atk}
                    if turn_a: zombie_a = nouveau_zombie
                    else: zombie_b = nouveau_zombie
                    await add_action_to_log(f"Un Zombie apparaît avec **{zombie_pv} PV** et **{zombie_atk} d'attaque**.")
                    await add_action_to_log(f"Le Zombie attaque immédiatement !")
                    first_strike_damage = random.randint(1, zombie_atk) * damage_multiplier
                    await apply_damage(defenseur['nom'], defenseur, nom_attaquant, attaquant ,first_strike_damage, add_action_to_log, turn_a)
            elif copied_power == "Bénédiction":
                soin = math.ceil(attaquant['max_pv'] * 0.20)
                await add_action_to_log(f"✨ {attaquant['nom']} active **Bénédiction** et soigne tous ses alliés de **{soin}** PV !")
                for personnage in team_attaquant:                                                
                    if personnage['pv'] > 0:                                                    
                        await apply_heal(personnage, soin, "Bénédiction")
                
            elif copied_power == "Poison":
                await add_action_to_log(f"☠️ {attaquant['nom']} active **Poison** !")
                defenseur['poison_stacks'] += 1
                await add_action_to_log(f"{defenseur['nom']} est maintenant empoisonné (Charge: {defenseur['poison_stacks']}) !")
                if 'malade' not in defenseur.get('etats', []):                                                
                    # On utilise .get() pour la sécurité, même si on sait que 'etats' existe.                                                
                    defenseur['etats'].append('malade')                                                
                    await add_action_to_log(f"🤒 À cause du poison, {nom_defenseur} est maintenant **Malade** et ne peut plus être soigné !")
            elif copied_power == "Elan de puissance":
                existing_effect = next((e for e in attaquant['effects'] if e['name'] == 'Élan de puissance'), None)
                if existing_effect:
                    await add_action_to_log(f"⚡ {attaquant['nom']} intensifie son **Élan de puissance** !")
                    existing_effect['value'] += 2
                    existing_effect['duration'] -= 1
                else:
                    await add_action_to_log(f"💪 {attaquant['nom']} active **Élan de puissance** !")
                    attaquant['effects'].append({'name': 'Élan de puissance', 'type': 'attack_buff', 'value': 5, 'duration': 5})
                recalculate_and_update_attack(attaquant)
                await add_action_to_log(f"Son attaque passe à **{attaquant['attaque']}** !", delay=0.5)
            elif copied_power == "Talon d'Achille":
                await add_action_to_log(f"🎯 {attaquant['nom']} active **Talon d'Achille** !")
                if turn_a: team_a_talon_active = True
                else: team_b_talon_active = True
                await add_action_to_log("Les prochains dégâts de son équipe perceront toutes les défenses.", delay=0.5)
            elif copied_power == "Chaos":
                await add_action_to_log(f"🌀 {attaquant['nom']} déchaîne le **Chaos** !")
                liste_pouvoirs_disponibles = [p_info for p_nom, p_info in self.bot.catalogue_de_pouvoirs.items() if p_nom not in ["Chaos", "Mimétisme"]]
                pouvoir_choisi = random.choice(liste_pouvoirs_disponibles)
                await add_action_to_log(f"✨ Le Chaos se manifeste sous la forme de... **{pouvoir_choisi['nom']}** !")
                await activate_copied_power(pouvoir_choisi['nom'], attaquant, defenseur, turn_a, nom_attaquant, nom_defenseur,)
            elif copied_power == "Mimétisme":
                await add_action_to_log(f"**Mimétisme** ne peut pas être copié.", delay=0.5)
            elif copied_power == "Roboréparation":        
                soin = 30        
                await add_action_to_log(f"🔧 {nom_attaquant} copie et active **Roboréparation** !")        
                await apply_heal(attaquant, soin, "Roboréparation")
            elif copied_power == "Changement tactique":                                            
                                            # On cherche les alliés vivants sur le banc                                            
                allies_banc_vivants = [p for p in team_attaquant if p['pv'] > 0 and p != attaquant]                                            
                if allies_banc_vivants:                                                
                    # On trouve celui avec le plus de PV                                                
                    cible_swap = max(allies_banc_vivants, key=lambda p: p['pv'])                                                
                    await add_action_to_log(f"⚙️ {nom_attaquant} copie **Changement tactique** et échange sa place avec **{cible_swap['nom']}** !")                                                                                                
                    # On gère les effets de sortie et d'entrée                                                
                    await handle_character_swap_out(attaquant)                                                
                    if turn_a: active_a = cible_swap                                                
                    else: active_b = cible_swap                                                
                    attaquant = cible_swap # Le nouvel attaquant est la cible du swap                                                
                    await handle_character_swap_in(attaquant, defenseur, )                                            
                else:                                                
                    await add_action_to_log(f"⚙️ {nom_attaquant} tente d'utiliser **Changement tactique**, mais n'a aucun allié sur le banc !")
            elif copied_power == "Catalyseur":        
                await add_action_to_log(f"🔬 {nom_attaquant} active **Catalyseur** !")        
                if turn_a:            
                    catalyseur_bonus_a = 0.10        
                else:            
                    catalyseur_bonus_b = 0.10        
                    await add_action_to_log("Les chances de changement automatique de son équipe augmentent pour ce tour !")
            else:
                await add_action_to_log(f"Le pouvoir **{copied_power}** n'a pas pu être copié correctement.", delay=0.5)

        async def apply_damage(nom_defenseur_str, defenseur_obj, nom_attaquant_str, attaquant_obj, raw_damage, log_func, is_attaquant_team_a, source: str = "standard"):
            nonlocal team_a_poulets, team_b_poulets, zombie_a, zombie_b, team_a_talon_active, team_b_talon_active

            if 'bandeau_invincible' in defenseur_obj.get('etats', []):                
                await log_func(f"🎗️ La détermination du Bandeau rouge protège **{defenseur_obj['nom']}** ! Il ne subit aucun dégât !")                
                return 0 # Annule tous les dégâts entrants.     
                   
            is_talon_active = (is_attaquant_team_a and team_a_talon_active) or (not is_attaquant_team_a and team_b_talon_active)            
            damage_final = 0
        

            # --- CHEMIN 1 : L'ATTAQUE EST SOUS L'EFFET DE TALON D'ACHILLE ---
            if is_talon_active:
                await log_func("🎯 L'attaque perce TOUTES les défenses grâce au **Talon d'Achille** !")
                damage_final = raw_damage # Les dégâts finaux sont les dégâts bruts
                
                # On consomme l'effet Talon d'Achille
                if is_attaquant_team_a: team_a_talon_active = False
                else: team_b_talon_active = False

            # --- CHEMIN 2 : L'ATTAQUE EST NORMALE (PAS DE TALON D'ACHILLE) ---
            else:
                # Étape 2.1 : Interception par le Zombie adverse
                if is_attaquant_team_a and zombie_b:
                    await log_func(f"🧟 Le Zombie de {nom_adversaire} intercepte l'attaque !")
                    zombie_b['pv'] -= raw_damage
                    await log_func(f"🩸 Le Zombie subit **{raw_damage}** pts de dégâts. (PV restants : {max(0, zombie_b['pv'])})")
                    if zombie_b['pv'] <= 0:
                        await log_func(f"☠️ Le Zombie de {nom_adversaire} est détruit !")
                        zombie_b = None
                    update_embed_fields()
                    await log_message.edit(embed=embed)
                    return raw_damage # L'action s'arrête ici, la cible principale n'est pas touchée

                elif not is_attaquant_team_a and zombie_a:
                    await log_func(f"🧟 Votre Zombie intercepte l'attaque !")
                    zombie_a['pv'] -= raw_damage
                    await log_func(f"🩸 Le Zombie subit **{raw_damage}** pts de dégâts. (PV restants : {max(0, zombie_a['pv'])})")
                    if zombie_a['pv'] <= 0:
                        await log_func(f"☠️ Votre Zombie est détruit !")
                        zombie_a = None
                    update_embed_fields()
                    await log_message.edit(embed=embed)
                    return raw_damage # L'action s'arrête ici

                # Étape 2.2 : Interception par le Poulet adverse
                if is_attaquant_team_a and team_b_poulets > 0:
                    await log_func(f"🐔 Un poulet adverse tank les dégâts pour {nom_defenseur_str} !")
                    team_b_poulets -= 1
                    update_embed_fields()
                    await log_message.edit(embed=embed)
                    return 0 # L'action s'arrête ici

                elif not is_attaquant_team_a and team_a_poulets > 0:
                    await log_func(f"🐔 Un de vos poulets tank les dégâts pour {nom_defenseur_str} !")
                    team_a_poulets -= 1
                    update_embed_fields()
                    await log_message.edit(embed=embed)
                    return 0 # L'action s'arrête ici

                # Étape 2.3 : Calcul de l'armure (si aucune interception n'a eu lieu)
                damage_final = raw_damage
                if defenseur_obj.get('armure', 0) > 0:
                    armure_actuelle = defenseur_obj.get('armure', 0)
                    damage_final = max(0, raw_damage - armure_actuelle)
                    if damage_final < raw_damage and raw_damage > 0: await log_func(f"🛡️ L'armure de {nom_defenseur_str} bloque **{raw_damage - damage_final}** dégâts !", delay=0.5)
                    if raw_damage > 0 and damage_final == 0:
                        await log_func(f"✨ L'armure pare l'intégralité du coup et se brise ! L'armure de {nom_defenseur_str} retombe à 0.", delay=0.5)
                        defenseur_obj['armure'] = 0
            # --- APPLICATION FINALE DES DÉGÂTS ET EFFETS POST-DÉGÂTS ---
            # Que l'attaque soit passée par le chemin 1 (Talon) ou 2 (Normal), elle arrive ici.
            if 'affaibli' in defenseur_obj.get('etats', []) and defenseur_obj['pv'] < defenseur_obj['max_pv']:                
                        if damage_final > 0: # On applique le bonus que si des dégâts passent                    
                            await log_func(f"🩸 {nom_defenseur_str} est affaibli et subit des dégâts augmentés !", delay=0.5)                    
                            damage_final = math.ceil(damage_final * 1.5)

            # --- MODIFICATION : On capture les PV avant d'appliquer les dégâts ---            
            pv_avant = defenseur_obj['pv']            
            defenseur_obj['pv'] -= damage_final            
            await log_func(f"🩸 {nom_defenseur_str} subit **{damage_final}** pts de dégâts. (PV restants : {max(0, defenseur_obj['pv'])})")                        
            # --- DÉBUT DE L'AJOUT : LOGIQUE D'EXÉCUTION DU HACHOIR ---            
            execute_threshold = defenseur_obj['max_pv'] * 0.25            
            # On vérifie si l'attaquant a le Hachoir, si la source est autorisée,             
            # si on a franchi le seuil, et si la cible n'était pas déjà morte.            
            if (attaquant_obj.get("equipement") and attaquant_obj["equipement"].get("nom") == "Hachoir" and                
                source == "standard" and                
                defenseur_obj['pv'] < execute_threshold and pv_avant >= execute_threshold and defenseur_obj['pv'] > 0):                                
                    await log_func(f"🪓 Le Hachoir de {nom_attaquant_str} s'abat ! **Exécution !**", delay=0.5)                
                    defenseur_obj['pv'] = 0
            
            is_dead = defenseur_obj['pv'] <= 0            
            has_bandeau = defenseur_obj.get("equipement") and defenseur_obj["equipement"].get("nom") == "Bandeau rouge"            
            bandeau_ready = not defenseur_obj.get('bandeau_used_this_stint', False)            
            if is_dead and has_bandeau and bandeau_ready:                
                await log_func(f"🎗️ Le Bandeau rouge de **{defenseur_obj['nom']}** s'active ! Il s'accroche à la vie !")                
                defenseur_obj['pv'] = 1 # Il survit à 1 PV                
                defenseur_obj['bandeau_used_this_stint'] = True                
                if 'bandeau_invincible' not in defenseur_obj.get('etats', []):                    
                    defenseur_obj['etats'].append('bandeau_invincible')                
                    await log_func(f"🩸 Il survit avec **1 PV** et ne pourra pas être achevé ce tour-ci.")
            # La capacité de la Samouraï s'active ici, après que les dégâts finaux aient été calculés et appliqués.
            if defenseur_obj.get('nom') == "La Samourai" and damage_final > 0:
                armure_gagnee = math.ceil(damage_final * 0.5)
                defenseur_obj['armure'] += armure_gagnee
                await log_func(f"💪 {nom_defenseur_str} gagne **{armure_gagnee}** points d'armure !")
            
                        # ... juste après le bloc "if defenseur_obj.get('nom') == "La Samourai" ...

            # --- DÉBUT DE L'AJOUT : LOGIQUE DE LA CÔTE ÉPINEUSE ---
            # On vérifie si l'attaque n'était PAS sous Talon d'Achille, que des dégâts ont été faits,
            # et que le défenseur porte bien l'équipement.
            if not is_talon_active and damage_final > 0 and defenseur_obj.get("equipement") and defenseur_obj["equipement"].get("nom") == "Côte épineuse": 
                    reflected_damage = math.ceil(damage_final * 0.5) * damage_multiplier
                    await log_func(f"🌵 La Côte épineuse de {nom_defenseur_str} s'active et renvoie **{reflected_damage}** pts de dégâts !", delay=0.5)
                    final_reflected_damage = reflected_damage                    
                    # L'attaquant devient ici le défenseur des dégâts de renvoi                    
                    if 'affaibli' in attaquant_obj.get('etats', []) and attaquant_obj['pv'] < attaquant_obj['max_pv']:                        
                        await log_func(f"🩸 {nom_attaquant_str} est affaibli et subit des dégâts de recul augmentés !", delay=0.5)                        
                        final_reflected_damage = math.ceil(final_reflected_damage * 1.5)
                    # On applique les dégâts de renvoi à l'attaquant.
                    # Note : les dégâts de renvoi ne peuvent pas être renvoyés à leur tour, pour éviter une boucle infinie.
                    attaquant_obj['pv'] -= final_reflected_damage
                    await log_func(f"🩸 {nom_attaquant_str} subit les dégâts de recul. (PV restants : {max(0, attaquant_obj['pv'])})")
                    
            if damage_final > 0 and defenseur_obj.get('capacite_unique') == "Toxines":                
                reflected_damage = damage_final # Renvoie 100% des dégâts subis                
                await log_func(f"🦠 La capacité **Toxines** de {nom_defenseur_str} s'active et renvoie **{reflected_damage}** pts de dégâts !", delay=0.5)                                
                final_reflected_damage = reflected_damage                
                if 'affaibli' in attaquant_obj.get('etats', []) and attaquant_obj['pv'] < attaquant_obj['max_pv']:                    
                    await log_func(f"🩸 {nom_attaquant_str} est affaibli et subit des dégâts de recul augmentés !", delay=0.5)                    
                    final_reflected_damage = math.ceil(final_reflected_damage * 1.5)                                
                attaquant_obj['pv'] -= final_reflected_damage                
                await log_func(f"🩸 {nom_attaquant_str} subit les dégâts toxiques. (PV restants : {max(0, attaquant_obj['pv'])})")

            update_embed_fields()
            await log_message.edit(embed=embed)
            return damage_final
        

        # --- NOUVELLE FONCTION CENTRALISÉE ---
        async def handle_death_effects(mort, team_mort, attaquant, team_attaquant, tour_actif_a):
            """Gère tous les effets qui se déclenchent à la mort d'un personnage."""
            
            # On détermine les noms pour les logs
            nom_mort_str = f"{nom_joueur if not tour_actif_a else nom_adversaire} **{mort['nom']}**"
            nom_attaquant_str = f"{nom_joueur if tour_actif_a else nom_adversaire} **{attaquant['nom']}**"

            survivants_propres = [p for p in team_mort if p['pv'] > 0]

            # Effet "Martyrdom" de la Couronne
            if (mort.get("equipement") and mort["equipement"].get("nom") == "La Couronne"):
                if len(survivants_propres) > 0:
                    await add_action_to_log(f"👑 En mourant, la Couronne de **{mort['nom']}** maudit tout le monde dans un dernier souffle !")
                    
                    attaquant['pv'] = 1
                    await add_action_to_log(f"💥 {nom_attaquant_str} est pris dans la malédiction et se retrouve à **1 PV** !")
                    
                    for allie_restant in survivants_propres:
                        allie_restant['pv'] = 1
                        nom_equipe_defenseur = nom_joueur if not tour_actif_a else nom_adversaire
                        nom_allie_formate = f"{nom_equipe_defenseur} **{allie_restant['nom']}**"
                        await add_action_to_log(f"💥 La malédiction collatérale laisse {nom_allie_formate} à **1 PV** !")

            # Effet "Last Stand" de la Couronne
            if len(survivants_propres) == 1:
                dernier_survivant = survivants_propres[0]
                if (dernier_survivant.get("equipement") and dernier_survivant["equipement"].get("nom") == "La Couronne" and not dernier_survivant.get('couronne_active')):
                    dernier_survivant['couronne_active'] = True
                    dernier_survivant['pv'] = dernier_survivant['max_pv']
                    await add_action_to_log(f"👑 **{dernier_survivant['nom']}** est le dernier survivant ! La Couronne révèle son vrai pouvoir !")
                    await add_action_to_log(f"❤️‍🩹 **{dernier_survivant['nom']}** est entièrement soigné et ses attaques sont désormais **brutes** !")
            if mort.get('nom') == "Robot expérimental":        
                await add_action_to_log("💥 Le **Robot expérimental** explose et disparaît définitivement du terrain !", delay=0.5)        
                # On le retire de la liste de son équipe pour qu'il n'apparaisse plus        
                try:            
                    team_mort.remove(mort)        
                except ValueError:            
                    # Sécurité au cas où le robot aurait déjà été retiré pour une raison quelconque            
                    pass 
        # --- FIN DE LA NOUVELLE FONCTION ---

    
        
        # --- NOUVELLE FONCTION DE SOIN CENTRALISÉE ---
        async def apply_heal(target_character, heal_amount, source_name):
            """
            Applique un soin à un personnage, mais seulement s'il n'est pas malade.
            Retourne le montant de PV réellement soigné.
            """
            if 'malade' in target_character.get('etats', []):
                # Le personnage est malade, le soin est bloqué.
                await add_action_to_log(f"🤒 L'état **Malade** de **{target_character['nom']}** empêche le soin de *{source_name}* !")
                return 0 # Aucun soin n'a été appliqué.
            else:
                # Le personnage n'est pas malade, on applique le soin.
                pv_avant = target_character['pv']
                # On s'assure de ne pas dépasser les PV max.
                target_character['pv'] = min(target_character['max_pv'], target_character['pv'] + heal_amount)
                pv_soignes = target_character['pv'] - pv_avant
                
                # On annonce le soin seulement si des PV ont été rendus.
                if pv_soignes > 0:
                    await add_action_to_log(f"❤️‍🩹 **{target_character['nom']}** récupère **{pv_soignes}** PV grâce à *{source_name}* !")
                return pv_soignes
        # --- FIN DE LA FONCTION DE SOIN ---


        # --- NOUVELLE FONCTION POUR GÉRER LES ÉCHANGES ---
        async def handle_character_swap_out(character_leaving):
            """Gère tous les effets qui se déclenchent quand un personnage quitte le terrain."""
            
            # Logique de la Pierre du changement
            if character_leaving.get("equipement") and character_leaving["equipement"].get("nom") == "Pierre du changement":
                character_leaving['bonus_degats'] += 1
                await add_action_to_log(f"💎 La Pierre du changement de **{character_leaving['nom']}** s'illumine ! Il gagne +1 dégât permanent. (Total: +{character_leaving['bonus_degats']})")
            elif character_leaving.get("equipement") and character_leaving["equipement"].get("nom") == "Pierre du changement corrompu":                
                character_leaving['bonus_degats'] += 4                
                await add_action_to_log(f"⚫ La Pierre corrompue de **{character_leaving['nom']}** pulse d'énergie ! Il gagne **+4** dégâts permanents. (Total: +{character_leaving['bonus_degats']})")
            # On centralise aussi les autres logiques de "nettoyage" ici
            await remove_grimoire_buff(character_leaving)
            await remove_baguette_buff(character_leaving)
            character_leaving['effects'] = []
            recalculate_and_update_attack(character_leaving)
            if character_leaving.get('nom') == "Le Robot": character_leaving['ability_used_this_stint'] = False
            character_leaving['bandeau_used_this_stint'] = False
            if character_leaving.get('nom') == "Robot mage":                    
                 if character_leaving.get('bonus_degats', 0) > 0:                        
                     await add_action_to_log(f"🔮 En quittant le terrain, le cristal de **{character_leaving['nom']}** perd sa charge.")                        
                     character_leaving['bonus_degats'] = 3
        # --- FIN DE LA NOUVELLE FONCTION ---

                # --- NOUVELLE FONCTION POUR GÉRER LES EFFETS D'ENTRÉE ---
        async def handle_character_swap_in(character_entering, opponent):
            """Gère tous les effets qui se déclenchent quand un personnage arrive sur le terrain."""
            
            # On applique les buffs d'équipement comme Grimoire et Baguette
            await apply_grimoire_buff(character_entering)
            await apply_baguette_buff(character_entering)

            # Capacité unique : Robot épée ("Assaut éclair")
            if character_entering.get('nom') == "Robot épée":
                await add_action_to_log(f"⚔️ **Assaut éclair !** Le Robot épée attaque en arrivant !")
                # On simule une attaque de base
                base_damage = await async_roll_for_damage(character_entering, 1, character_entering['attaque']) * damage_multiplier
                raw_damage, did_crit = calculate_final_damage(base_damage, character_entering)
                if did_crit: await add_action_to_log("💥 **COUP CRITIQUE !**")
                
                # On détermine les bons noms pour l'affichage des dégâts
                # (C'est un peu complexe car on ne sait pas quelle équipe est l'attaquant ici)
                is_team_a = any(p['nom'] == character_entering['nom'] for p in team_a)
                nom_attaquant_str = f"{nom_joueur} **{character_entering['nom']}**" if is_team_a else f"{nom_adversaire} **{character_entering['nom']}**"
                nom_defenseur_str = f"{nom_adversaire} **{opponent['nom']}**" if is_team_a else f"{nom_joueur} **{opponent['nom']}**"

                await apply_damage(nom_defenseur_str, opponent, nom_attaquant_str, character_entering, raw_damage, add_action_to_log, is_team_a)

            # Capacité unique : Robot bouclier ("Armure de secours")
            if character_entering.get('nom') == "Robot bouclier":
                character_entering['armure'] += 5
                await add_action_to_log(f"🛡️ **Armure de secours !** Le Robot bouclier gagne **5** points d'armure en arrivant.")
        # --- FIN DE LA NOUVELLE FONCTION ---


     
        def find_next_survivor(team):            
            return next((p for p in team if p['pv'] > 0), None)
        
        # Dans lancer_combat_engine, juste avant le "try:" de la boucle while

        # --- NOUVELLE FONCTION DE GESTION DE VICTOIRE ---
        async def _handle_victory(winner_name, team_a_final, team_b_final,is_pve=False) :
            try:
                print(f"[_handle_victory] Début - Winner: {winner_name}")
                
                # 1. Nettoyage de la durabilité AVANT de retourner
                for team_index, team in enumerate([team_a_final, team_b_final]):
                    print(f"[_handle_victory] Traitement équipe {team_index}")
                    for character in team:
                        print(f"[_handle_victory] Personnage {character.get('nom')} - PV: {character['pv']}")
                        if character['pv'] >= 0:
                            # Nettoyage des pouvoirs épuisés
                            if 'pouvoirs' in character and character['pouvoirs']:                        
                                for i in range(len(character['pouvoirs'])):                            
                                    power = character['pouvoirs'][i]                            
                                    if power and power.get('durability', 1) <= 0:                                
                                        print(f"[_handle_victory] Pouvoir {power.get('nom')} épuisé")
                                        character['pouvoirs'][i] = None
                            
                            # Décrémentation des équipements
                            if character.get('equipement'):
                                print(f"[_handle_victory] Équipement trouvé: {character['equipement'].get('nom')}")
                                if 'durability' in character['equipement']:
                                    print(f"[_handle_victory] Réduction de durabilité pour {character['nom']} : Avant = {character['equipement']['durability']}")
                                    character['equipement']['durability'] -= 1
                                    print(f"[_handle_victory] Après = {character['equipement']['durability']}")
                                    if character['equipement']['durability'] <= 0:
                                        print(f"[_handle_victory] Équipement cassé")
                                        character['equipement'] = None
                                else:
                                    print(f"[_handle_victory] Pas de durability trouvée dans l'équipement")
                
                # 2. Détermination de l'ID du gagnant et des survivants
                print(f"[_handle_victory] Récupération du GameManager")
                game_manager = self.bot.get_cog('GameManagerCog')
                game_state = game_manager.active_games.get(log_message.channel.id) if game_manager else None
                
                winner_id = None
                if game_state:
                    if not is_pve:
                        for p_id, p_data in game_state['players'].items():
                            if p_data['member'].name == winner_name:
                                winner_id = p_id
                                break
                    else:
                        player_data = game_state.get('player')                        
                        if player_data and winner_name == player_data['member'].name:                           
                            winner_id = player_data['member'].id
                
                winning_team = team_a_final if winner_name == nom_joueur else team_b_final
                survivors = len([p for p in winning_team if p['pv'] > 0])
                print(f"[_handle_victory] Winners: {survivors} survivants")

                # 3. Message de fin et suppression de l'état
                await add_action_to_log(f"\n🏆 **VICTOIRE POUR {winner_name.upper()} !** 🏆")
                embed.title = f"⚔️ {titre_combat} Terminé ! ⚔️"
                self._delete_combat_state(log_message.channel.id)

                print(f"[_handle_victory] Victoire traitée avec succès")

                # 4. Retourner le dictionnaire complet
                return {
                    'winner_id': winner_id,
                    'survivors': survivors,
                    'team_a_final': team_a_final,
                    'team_b_final': team_b_final
                }
            except Exception as e:
                print(f"[_handle_victory] ❌ ERREUR: {e}")
                import traceback
                traceback.print_exc()
                raise
        
    
        try:
            while True:
                print(f"Tour {tour_count} commence...")
                await asyncio.sleep(2.5)
                tour_count += 1
                print(f"Tour {tour_count} en cours...")

                try:           
                    # Exemple : vérifiez les actions après chaque opération asynchrone           
                    await log_message.edit(embed=embed)           
                    print("Message Discord édité.")  # Log pour confirmer l'édition      
                except Exception as e:           
                    print(f"Erreur lors de l'édition du message : {e}")
                attaquant, defenseur = (active_a, active_b) if turn_a else (active_b, active_a)
                team_attaquant, team_defenseur = (team_a, team_b) if turn_a else (team_b, team_a)
                nom_attaquant = f"{nom_joueur} **{attaquant['nom']}**" if turn_a else f"{nom_adversaire} **{attaquant['nom']}**"
                nom_defenseur = f"{nom_adversaire} **{defenseur['nom']}**" if turn_a else f"{nom_joueur} **{defenseur['nom']}**"
                
                log_entry = f"**Tour {tour_count}**"
                combat_log.append(log_entry)
                
                # Capacité unique : Cristal Robotique                    
                if attaquant.get('nom') == "Robot mage":                        
                    attaquant['bonus_degats'] += 1                        
                    await add_action_to_log(f"🔮 Le Cristal robotique de **{attaquant['nom']}** charge ! (Bonus total: +{attaquant['bonus_degats']})")

                            # --- Vérification et gestion de Tempo ---
                if turn_a:
                    # C'est le tour de l'équipe A
                    if not is_bonus_turn_a: # On vérifie si ce n'est pas déjà un tour bonus
                        if attaquant.get("equipement") and attaquant["equipement"]["nom"] == "Tempo" and attaquant['pv'] >= attaquant.get('pv_at_turn_end', attaquant['pv']):
                            tempo_pending_a = True # On prépare le tour bonus pour l'équipe A
                            await add_action_to_log(f"🍃 {nom_attaquant} n'a subi aucun dégât, **Tempo** se prépare !")
                    is_bonus_turn_a = False # Dans tous les cas, on consomme le statut "tour bonus"
                else:
                    # C'est le tour de l'équipe B
                    if not is_bonus_turn_b:
                        if attaquant.get("equipement") and attaquant["equipement"]["nom"] == "Tempo" and attaquant['pv'] >= attaquant.get('pv_at_turn_end', attaquant['pv']):
                            tempo_pending_b = True # On prépare le tour bonus pour l'équipe B
                            await add_action_to_log(f"🍃 {nom_attaquant} n'a subi aucun dégât, **Tempo** se prépare !")
                    is_bonus_turn_b = False # On consomme le statut "tour bonus"

                effects_to_remove = []
                for effect in attaquant['effects']:
                    effect['duration'] -= 1
                    if effect['duration'] <= 0:
                        effects_to_remove.append(effect)
                if effects_to_remove:
                    for effect in effects_to_remove:
                        attaquant['effects'].remove(effect)
                        await add_action_to_log(f"💨 L'effet **{effect['name']}** de {nom_attaquant} se dissipe !", delay=0.5)
                    recalculate_and_update_attack(attaquant) # Met à jour l'attaque après la suppression
                    update_embed_fields()
                    await log_message.edit(embed=embed)


                is_zombie_turn = (turn_a and zombie_a) or (not turn_a and zombie_b)
                if not is_zombie_turn:
                    combat_log[-1] += f" ({nom_attaquant})"

                if tour_count == 1 and not resumed_state:
                    # --- DÉBUT DU BLOC CORRIGÉ ---
                    
                    # 1. Vérification de la Couronne (Effet "Jealousy")
                    jealousy_triggered = False
                    for team, team_name in [(team_a, nom_joueur), (team_b, nom_adversaire)]:
                        bearers = [p for p in team if p.get("equipement") and p["equipement"].get("nom") == "La Couronne"]
                        if len(bearers) > 1:
                            jealousy_triggered = True
                            await add_action_to_log(f"👑 La Couronne n'accepte qu'un seul maître dans l'équipe de **{team_name}**... et punit les usurpateurs !")
                            for bearer in bearers:
                                bearer['pv'] = 0
                                await add_action_to_log(f"💀 **{bearer['nom']}** a été anéanti par le pouvoir de la Couronne !")
                    
                    # Si des morts ont eu lieu, on met à jour l'affichage immédiatement
                    if jealousy_triggered:
                        update_embed_fields()
                        await log_message.edit(embed=embed)

                        # 2. CONSÉQUENCE : Vérifier si le combat doit se terminer ou si les combattants actifs doivent changer
                        team_a_survivor = find_next_survivor(team_a)
                        team_b_survivor = find_next_survivor(team_b)

                        # Vérification de victoire immédiate
                        if not team_a_survivor:                     
                            return await _handle_victory(nom_joueur, team_a, team_b, is_pve)
                        
                        if not team_b_survivor:                                           
                            return await _handle_victory(nom_joueur, team_a, team_b, is_pve )
                        
                        # Mise à jour des combattants actifs s'ils sont morts
                        if active_a['pv'] <= 0:
                            active_a = team_a_survivor
                            await add_action_to_log(f"▶️ Suite à cette hécatombe, {nom_joueur} **{active_a['nom']}** devient le combattant actif !")
                        
                        if active_b['pv'] <= 0:
                            active_b = team_b_survivor
                            await add_action_to_log(f"▶️ Suite à cette hécatombe, {nom_adversaire} **{active_b['nom']}** devient le combattant actif !")

                    # 3. Application des buffs sur les personnages (potentiellement nouveaux) actifs
                    await apply_grimoire_buff(active_a)                    
                    await apply_grimoire_buff(active_b)
                    await apply_baguette_buff(active_a)                 
                    await apply_baguette_buff(active_b)
                    
                    # Mise à jour finale de l'affichage avant le début du tour
                    update_embed_fields()
                    await log_message.edit(embed=embed)
                    # --- FIN DU BLOC CORRIGÉ ---
            
                damage_multiplier = 2 if tour_count >= 50 else 1
                if tour_count == 50:
                    await add_action_to_log(" Bientôt la fin ! Les dégâts sont maintenant doublés jusqu'à la fin du combat !")

                if attaquant.get('poison_stacks', 0) > 0:
                    poison_damage = attaquant['poison_stacks'] * damage_multiplier
                    await add_action_to_log(f"☠️ {nom_attaquant} subit **{poison_damage}** dégâts de poison !", delay=0.5)
                    attaquant['pv'] -= poison_damage
                    if attaquant.get('poison_stacks', 0) == 0 and 'malade' in attaquant.get('etats', []):                        
                        attaquant['etats'].remove('malade')                        
                        await add_action_to_log(f"✅ Le poison s'est dissipé ! {nom_attaquant} n'est plus **Malade**.")
                    update_embed_fields()
                    await log_message.edit(embed=embed)
                    if attaquant['pv'] <= 0:
                        attaquant['pv'] = 0
                        await add_action_to_log(f"☠️ {nom_attaquant} succombe au poison !")
                        ancien_attaquant = attaquant
                        await handle_death_effects(mort=ancien_attaquant, team_mort=team_attaquant, attaquant=ancien_attaquant, team_attaquant=team_attaquant, tour_actif_a=turn_a)                        
                        await remove_grimoire_buff(ancien_attaquant)
                        await remove_baguette_buff(ancien_attaquant)
                        prochain_combattant = next((p for p in team_attaquant if p['pv'] > 0), None)
                        if not prochain_combattant:                        
                            winner_name = nom_adversaire if turn_a else nom_joueur                      
                            return await _handle_victory(winner_name, team_a, team_b, is_pve)
                        else:
                            if turn_a: active_a = prochain_combattant
                            else: active_b = prochain_combattant
                            await handle_character_swap_in(prochain_combattant, defenseur)
                            await add_action_to_log(f"▶️ {('**' if turn_a else nom_adversaire + ' **')}{prochain_combattant['nom']}** entre en scène !")
                            turn_a = not turn_a
                            update_embed_fields()
                            await log_message.edit(embed=embed)
                            continue
                
                            # ===================================================================
                # =================== NOUVELLE STRUCTURE D'ACTION ===================
                # ===================================================================
                if attaquant.get("equipement") and attaquant["equipement"].get("nom") == "Grimoire interdit":                    
                    if attaquant.get('grimoire_turns_left', 0) > 0:                        
                        attaquant['grimoire_turns_left'] -= 1                        
                        await add_action_to_log(f"⏳ Le bonus du Grimoire de **{attaquant['nom']}** durera encore {attaquant['grimoire_turns_left']} tour(s).", delay=0.5)                        
                        if attaquant['grimoire_turns_left'] == 0:                            
                            await remove_grimoire_buff(attaquant) # Le buff expire

                if (turn_a and team_a_is_stunned) or (not turn_a and team_b_is_stunned):
                    await add_action_to_log(f"⏳ {nom_attaquant} est pris dans le bourbier et ne peut pas agir ce tour-ci !")
                    if turn_a: team_a_is_stunned = False
                    else: team_b_is_stunned = False

                elif (turn_a and team_a_bombardement_stun) or (not turn_a and team_b_bombardement_stun):
                    await add_action_to_log(f"✈️ {nom_attaquant} se remet du Bombardement et saute entièrement son tour !")
                    if turn_a: team_a_bombardement_stun = False
                    else: team_b_bombardement_stun = False

                elif attaquant.get('nom') == "Le Robot" and attaquant.get('repair_mode_active', False):
                    soin = math.ceil(attaquant['max_pv'] * 0.25)
                    await apply_heal(attaquant, soin, "son protocole de réparation")
                    attaquant['repair_turns_left'] -= 1
                    await add_action_to_log(f"🔧 {nom_attaquant} se répare de **{soin}** PV !")
                    if attaquant['repair_turns_left'] <= 0:
                        attaquant['repair_mode_active'] = False
                        await add_action_to_log(f"✅ Réparation terminée !")


                elif turn_a and zombie_a:
                    combat_log[-1] += " (🧟 Tour du Zombie)"
                    await add_action_to_log(f"Le Zombie attaque !")
                    zombie_damage = await async_roll_for_damage(attaquant, 1, zombie_a['attaque']) * damage_multiplier
                    await add_action_to_log(f"💥 Le Zombie attaque avec une puissance de **{zombie_damage}** !")
                    await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant ,zombie_damage, add_action_to_log, True, source="zombie")
                    if defenseur['pv'] <= 0:
                        defenseur['pv'] = 0
                        await add_action_to_log(f"☠️ {nom_defenseur} est hors de combat !")
                        ancien_defenseur = defenseur
                        await handle_death_effects(mort=ancien_defenseur, team_mort=team_defenseur, attaquant=attaquant, team_attaquant=team_attaquant, tour_actif_a=turn_a)                       
                        await remove_grimoire_buff(ancien_defenseur)
                        await remove_baguette_buff(ancien_defenseur)
                        prochain_combattant = next((p for p in team_defenseur if p['pv'] > 0), None)
                        if not prochain_combattant:                        
                            winner_name = nom_joueur if turn_a else nom_adversaire                        
                            return await _handle_victory(winner_name, team_a, team_b, is_pve)
                        else:
                            active_b = prochain_combattant
                            defenseur = active_b
                            await handle_character_swap_in(prochain_combattant, attaquant)
                            await add_action_to_log(f"▶️ {nom_adversaire} **{prochain_combattant['nom']}** entre en scène !")
                    
                
                elif not turn_a and zombie_b:
                    combat_log[-1] += f" (🧟 Tour du Zombie de {nom_adversaire})"
                    await add_action_to_log(f"Le Zombie de {nom_adversaire} attaque !")
                    zombie_damage = await async_roll_for_damage(attaquant, 1, zombie_b['attaque']) * damage_multiplier
                    await add_action_to_log(f"💥 Le Zombie attaque avec une puissance de **{zombie_damage}** !")
                    await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant ,zombie_damage, add_action_to_log, False, source="zombie")
                    if defenseur['pv'] <= 0:
                        defenseur['pv'] = 0
                        await add_action_to_log(f"☠️ {nom_defenseur} est hors de combat !")
                        ancien_defenseur = defenseur
                        await handle_death_effects(mort=ancien_defenseur, team_mort=team_defenseur, attaquant=attaquant, team_attaquant=team_attaquant, tour_actif_a=turn_a)                      
                        await remove_grimoire_buff(ancien_defenseur)
                        await remove_baguette_buff(ancien_defenseur)
                        prochain_combattant = next((p for p in team_defenseur if p['pv'] > 0), None)
                        if not prochain_combattant:                        
                            winner_name = nom_joueur if turn_a else nom_adversaire                        
                            return await _handle_victory(winner_name, team_a, team_b, is_pve)
                        else:
                            active_a = prochain_combattant
                            defenseur = active_a
                            await handle_character_swap_in(prochain_combattant, attaquant)
                            await add_action_to_log(f"▶️ **{prochain_combattant['nom']}** entre en scène !")
                    
                else:
                    for p in attaquant.get("pouvoirs", []):
                        if p and p['nom'] == "Chaos":
                            p['activation'] = roll_dice(attaquant, 20, 80, mode='higher')[0]
                            await add_action_to_log(f"🎲 Le pouvoir Chaos de {nom_attaquant} a maintenant une chance d'activation de **{p['activation']}%** pour ce tour !", delay=0.5)
                            update_embed_fields()
                            await log_message.edit(embed=embed)
                        

                    if team_a_bouclier_magique and tour_count > bouclier_magique_expire_a:
                        team_a_bouclier_magique = False
                        await add_action_to_log("🛡️ Le Bouclier magique de votre équipe se dissipe.", delay=0.5)
                        update_embed_fields()
                        await log_message.edit(embed=embed)
                    if team_b_bouclier_magique and tour_count > bouclier_magique_expire_b:
                        team_b_bouclier_magique = False
                        await add_action_to_log(f"🛡️ Le Bouclier magique de {nom_adversaire} se dissipe.", delay=0.5)
                        update_embed_fields()
                        await log_message.edit(embed=embed)
                        
                    
                    if not turn_a and prescience_timer_a is not None:
                        prescience_timer_a -= 1
                        if prescience_timer_a <= 0:
                            base_damage = prescience_caster_a['attaque'] * (2 + prescience_damage_multiplier_a) * damage_multiplier                                                        
                            # On vérifie le critique en utilisant l'objet du lanceur                            
                            final_damage, did_crit = calculate_final_damage(base_damage, prescience_caster_a)                            
                            await add_action_to_log(f"🔮 **Prescience** de {prescience_caster_a['nom']} s'active ! (Dégâts de base: **{base_damage}**)")                            
                            if did_crit:                                
                                await add_action_to_log("💥 **COUP CRITIQUE !**")                                                        
                            # On passe le lanceur comme attaquant pour que la Côte Épineuse fonctionne correctement                            
                            await apply_damage(nom_defenseur, defenseur, "Prescience", prescience_caster_a, final_damage, add_action_to_log, False, source="prescience")                                                        
                            prescience_timer_a, prescience_damage_multiplier_a, prescience_caster_a = None, 0, None
                    elif turn_a and prescience_timer_b is not None:
                        prescience_timer_b -= 1
                        if prescience_timer_b <= 0:
                            base_damage = prescience_caster_b['attaque'] * (2 + prescience_damage_multiplier_b) * damage_multiplier                                                        
                            # On vérifie le critique en utilisant l'objet du lanceur                            
                            final_damage, did_crit = calculate_final_damage(base_damage, prescience_caster_b)                            
                            await add_action_to_log(f"🔮 **Prescience** de {prescience_caster_b['nom']} s'active ! (Dégâts de base: **{base_damage}**)")                            
                            if did_crit:                                
                                await add_action_to_log("💥 **COUP CRITIQUE !**")                                                        
                            # On passe le lanceur comme attaquant pour que la Côte Épineuse fonctionne correctement                            
                            await apply_damage(nom_defenseur, defenseur, "Prescience", prescience_caster_b, final_damage, add_action_to_log, False, source="prescience")                                                        
                            prescience_timer_b, prescience_damage_multiplier_b, prescience_caster_b = None, 0, None

                    qilin_vivante = next((p for p in team_attaquant if p['nom'] == "La Qilin" and p['pv'] > 0), None)
                    if qilin_vivante and attaquant['nom'] != "La Qilin":
                        soin = math.ceil(qilin_vivante['max_pv'] * 0.10)
                        await apply_heal(attaquant, soin, "l'aura de La Qilin")                        
                        update_embed_fields()                        
                        await log_message.edit(embed=embed)
                        
                    
                    necromancienne_morte = next((p for p in team_attaquant if p['nom'] == "La Nécromancienne" and p['pv'] <= 0 and not p.get('a_ressuscite', False)), None)
                    if necromancienne_morte and random.random() < 0.25:
                        necromancienne_morte['a_ressuscite'] = True
                        pv_zombie = math.ceil(necromancienne_morte['max_pv'] / 2)
                        necromancienne_morte['pv'] = pv_zombie
                        ancien_combattant = attaquant
                        await handle_character_swap_out(ancien_combattant)
                        if turn_a: active_a = necromancienne_morte
                        else: active_b = necromancienne_morte
                        attaquant = necromancienne_morte
                        await handle_character_swap_in(attaquant, defenseur)
                        nom_attaquant = f"**{attaquant['nom']}**" if turn_a else f"{nom_adversaire} **{attaquant['nom']}**"
                        await add_action_to_log(f"💀 **{necromancienne_morte['nom']}** revient du royaume des morts !")
                        await add_action_to_log(f"🧟 Elle prend la place de **{ancien_combattant['nom']}** avec **{pv_zombie}** PV !")
                        update_embed_fields()
                        await log_message.edit(embed=embed)
                    else:
                        is_paralyzed_by_fear = (turn_a and team_a_peur_bleu) or (not turn_a and team_b_peur_bleu)
                        personnages_vivants = [p for p in team_attaquant if p and p['pv'] > 0 and p != attaquant]
                        auto_swap_chance = 0.15 + (catalyseur_bonus_a if turn_a else catalyseur_bonus_b)     
                        if defenseur.get('capacite_unique') != "Robobarrière" and not is_paralyzed_by_fear and tour_count > 1 and random.random() < auto_swap_chance and personnages_vivants:
                            ancien_combattant = attaquant
                            await handle_character_swap_out(ancien_combattant)
                            nouveau_combattant = random.choice(personnages_vivants)
                            # Lorsqu'un personnage change ou est KO
                            await add_action_to_log(f"🔄 Changement ! {nom_attaquant} est remplacé par **{nouveau_combattant['nom']}** !")
                            if turn_a: active_a = nouveau_combattant
                            else: active_b = nouveau_combattant
                            attaquant = nouveau_combattant
                            await handle_character_swap_in(nouveau_combattant, defenseur)
                            nom_attaquant = f"**{attaquant['nom']}**" if turn_a else f"{nom_adversaire} **{attaquant['nom']}**"
                            update_embed_fields()
                            await log_message.edit(embed=embed)
                        if is_paralyzed_by_fear:
                            if turn_a: team_a_peur_bleu = False
                            else: team_b_peur_bleu = False

                
                    parieur_a_passe_son_tour = False
                    
                    effective_attack = attaquant['attaque']
                    is_parieur_ability_turn = attaquant.get('nom') == "Le Parieur" and attaquant.get('parieur_ability_ready')
                    if is_parieur_ability_turn:
                        await add_action_to_log(f"🎲 {nom_attaquant} lance une pièce !")
                        attaquant['parieur_ability_ready'] = False
                        if random.choice(['pile', 'face']) == 'face':
                            base_damage, did_crit = calculate_final_damage(effective_attack, attaquant) 
                            damage = base_damage * damage_multiplier     
                            await add_action_to_log(f"🤑 **FACE !** **{effective_attack}** pts de dégâts bruts !")        
                            if did_crit:            
                                    await add_action_to_log("💥 **COUP CRITIQUE !**")        
                            await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant ,damage, add_action_to_log, turn_a)
                        else:
                            await add_action_to_log(f"😥 **PILE !** Il passe son tour...")
                            parieur_a_passe_son_tour = True

                                
                                
                    if not parieur_a_passe_son_tour:
                        if attaquant['nom'] == "La Nécromancienne" and attaquant.get('a_ressuscite', False):
                            await add_action_to_log(f"🧟 {nom_attaquant} est en mode zombie et ne peut pas utiliser de pouvoirs.")
                        else:
                            pouvoirs_actives_ce_tour = 0
                            for slot in range(3):
                                pouvoir = attaquant.get("pouvoirs", [None, None, None])[slot]
                                if pouvoir:
                                    activation_chance = 0
                                    # AJOUT : Surcharge par le Grimoire                                    
                                    if attaquant.get("equipement") and attaquant["equipement"].get("nom") == "Grimoire interdit" and attaquant.get('grimoire_turns_left', 0) > 0:                                        
                                        activation_chance = 100                                    
                                    else:                                        
                                        # Votre logique existante pour calculer activation_chance
                                        if isinstance(pouvoir.get('activation'), int): activation_chance = pouvoir['activation']
                                        if pouvoir['nom'] != "Chaos":
                                            if pouvoir['nom'] == "Pile ou Face" and attaquant['nom'] == "Le Parieur": activation_chance = 50
                                            elif pouvoir['nom'] == "Armure" and attaquant['nom'] == "La Samourai": activation_chance = 50
                                            elif pouvoir['nom'] == "Batteries d'urgences" and attaquant['nom'] == "Le Robot": activation_chance = 50
                                            elif pouvoir['nom'] == "Nécromancie" and attaquant['nom'] == "La Nécromancienne": activation_chance = 50
                                            elif pouvoir['nom'] == "Bénédiction" and attaquant['nom'] == "La Qilin": activation_chance = 50
                                        
                                    if await async_roll_for_activation(attaquant, activation_chance):
                                        if 'durability' in pouvoir:                                            
                                            pouvoir['durability'] -= 1                                            
                                            await add_action_to_log(f"⚙️ La durabilité de **{pouvoir['nom']}** passe à {pouvoir['durability']}.", delay=0)
                                        # Vérification 1 : Cape Magique personnelle du défenseur                                        
                                        if defenseur.get("equipement") and defenseur["equipement"].get("nom") == "Cape magique" and defenseur.get('cape_magique_charges', 0) > 0:                                            
                                            # On vérifie si le pouvoir est blocable (pas un soin ou un buff personnel)                                            
                                            if pouvoir['nom'] not in ["Don", "Bouclier magique", "Armure", "Batteries d'urgences", "Nécromancie", "Bénédiction", "Elan de puissance"]:                                                
                                                defenseur['cape_magique_charges'] -= 1                                                
                                                await add_action_to_log(f"🧥 La Cape magique de {nom_defenseur} absorbe l'effet de **{pouvoir['nom']}** ! ({defenseur['cape_magique_charges']} charges restantes)")                                                
                                                if defenseur['cape_magique_charges'] == 0:                                                    
                                                    await add_action_to_log(f"💨 La Cape magique de {nom_defenseur} a perdu tout son pouvoir et se désintègre !")                                                
                                                continue # On passe au pouvoir suivant sans activer celui-ci
                                        is_shielded = (turn_a and team_b_bouclier_magique) or (not turn_a and team_a_bouclier_magique)
                                        if is_shielded and pouvoir['nom'] not in ["Don", "Bouclier magique", "Armure", "Batteries d'urgences", "Nécromancie", "Bénédiction", "Elan de puissance"]:
                                            await add_action_to_log(f"🛡️ Le Bouclier magique adverse bloque l'activation de **{pouvoir['nom']}** !")
                                            continue
                                        
                                        nom_pouvoir_a_activer = pouvoir['nom']
                                        
                                        if nom_pouvoir_a_activer == "Chaos":
                                            await add_action_to_log(f"🌀 {nom_attaquant} déchaîne le **Chaos** !")
                                            liste_pouvoirs_disponibles = [p_info for p_nom, p_info in self.bot.catalogue_de_pouvoirs.items() if p_nom not in ["Chaos", "Mimétisme"]]
                                            pouvoir_choisi = random.choice(liste_pouvoirs_disponibles)
                                            nom_pouvoir_a_activer = pouvoir_choisi['nom']
                                            await add_action_to_log(f"✨ Le Chaos se manifeste sous la forme de... **{nom_pouvoir_a_activer}** !")

                                        if nom_pouvoir_a_activer == "Frénésie":
                                            await add_action_to_log(f"🔥 {nom_attaquant} active **Frénésie** !")
                                            base_extra_damage = 0                                            
                                            if attaquant.get('couronne_active', False):                                                
                                                await add_action_to_log(f"👑 La Frénésie du survivant est **brute** et prévisible !")                                                
                                                base_extra_damage = effective_attack * damage_multiplier                                            
                                            else:                                                
                                                base_extra_damage = await async_roll_for_damage(attaquant, 1, effective_attack) * damage_multiplier
                                            extra_damage, did_crit = calculate_final_damage(base_extra_damage, attaquant)    
                                            if did_crit:        
                                                await add_action_to_log("💥 **COUP CRITIQUE !**")
                                            await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant ,extra_damage, add_action_to_log, turn_a)
                                        elif nom_pouvoir_a_activer == "Don":
                                            allies_blesses = [p for p in team_attaquant if p != attaquant and p['pv'] > 0 and p['pv'] < p['max_pv']]
                                            if allies_blesses:
                                                cible_soin = min(allies_blesses, key=lambda p: p['pv'])
                                                soin = math.ceil(attaquant['max_pv'] * 0.25)
                                                await add_action_to_log(f"🎁 {nom_attaquant} active **Don** !")                                                
                                                await apply_heal(cible_soin, soin, "Don")
                                        elif nom_pouvoir_a_activer == "Le Poulet":
                                            await add_action_to_log(f"🐔 {nom_attaquant} invoque un poulet protecteur !")
                                            if turn_a: team_a_poulets += 1
                                            else: team_b_poulets += 1
                                        elif nom_pouvoir_a_activer == "Bourbier":
                                            await add_action_to_log(f"🌪️ {nom_attaquant} active **Bourbier** et empêche {nom_defenseur} de jouer son prochain tour !")
                                            if turn_a: team_b_is_stunned = True
                                            else: team_a_is_stunned = True
                                        elif nom_pouvoir_a_activer == "Prescience":
                                            if turn_a:
                                                if prescience_timer_b is not None: prescience_damage_multiplier_b += 1
                                                else:
                                                    prescience_timer_b = 10
                                                    prescience_caster_b = attaquant
                                            else:
                                                if prescience_timer_a is not None: prescience_damage_multiplier_a += 1
                                                else:
                                                    prescience_timer_a = 10
                                                    prescience_caster_a = attaquant
                                            await add_action_to_log(f"🔮 {nom_attaquant} active ou renforce **Prescience** !")
                                        elif nom_pouvoir_a_activer == "Peur bleu":
                                            await add_action_to_log(f"😨 {nom_attaquant} active **Peur bleu** ! {nom_defenseur} ne pourra pas changer de personnage.")
                                            if turn_a: team_b_peur_bleu = True
                                            else: team_a_peur_bleu = True
                                        elif nom_pouvoir_a_activer == "Rugissement primal":
                                            personnages_banc_vivants = [p for p in team_defenseur if p['pv'] > 0 and p != defenseur]
                                            if personnages_banc_vivants:
                                                ancien_defenseur = defenseur
                                                await handle_character_swap_out(ancien_defenseur)
                                                nouveau_defenseur = random.choice(personnages_banc_vivants)
                                                await add_action_to_log(f"🗣️ {nom_attaquant} lance **Rugissement primal** ! {nom_defenseur} est remplacé par **{nouveau_defenseur['nom']}** !")
                                                if turn_a: active_b = nouveau_defenseur
                                                else: active_a = nouveau_defenseur
                                                defenseur = nouveau_defenseur
                                                nom_defenseur = f"{nom_adversaire} **{defenseur['nom']}**" if turn_a else f"**{defenseur['nom']}**"
                                                await handle_character_swap_in(nouveau_defenseur, attaquant)
                                            else:
                                                await add_action_to_log(f"🗣️ {nom_attaquant} lance **Rugissement primal**, mais il n'y a personne sur le banc !")
                                        elif nom_pouvoir_a_activer == "Bouclier magique":
                                            if attaquant.get("equipement") and attaquant["equipement"].get("nom") == "Cape magique" and attaquant.get('cape_magique_charges', 0) > 0:                                                
                                                await add_action_to_log(f"✨ {nom_attaquant} canalise l'énergie de sa **Cape magique** dans une attaque !")                                                                                              
                                                base_extra_damage = await async_roll_for_damage(attaquant, 1, effective_attack) * damage_multiplier                                                
                                                extra_damage, did_crit = calculate_final_damage(base_extra_damage, attaquant)                                                    
                                                if did_crit:                                                            
                                                    await add_action_to_log("💥 **COUP CRITIQUE !**")                                                
                                                await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant ,extra_damage, add_action_to_log, turn_a)
                                            else:
                                                await add_action_to_log(f"🛡️ {nom_attaquant} active **Bouclier magique** !")
                                                if turn_a:
                                                    team_a_bouclier_magique = True
                                                    bouclier_magique_expire_a = tour_count + 2
                                                else:
                                                    team_b_bouclier_magique = True
                                                    bouclier_magique_expire_b = tour_count + 2
                                        elif nom_pouvoir_a_activer == "Combo":
                                            multiplicateur = [0.25, 0.75, 1.50][min(pouvoirs_actives_ce_tour, 2)]
                                            base_combo_damage = math.ceil(effective_attack * multiplicateur) * damage_multiplier    
                                            damage, did_crit = calculate_final_damage(base_combo_damage, attaquant)    
                                            await add_action_to_log(f"💥 {nom_attaquant} active **Combo** et inflige **{base_combo_damage}** pts de dégâts de base !")    
                                            if did_crit:        
                                                await add_action_to_log("💥 **COUP CRITIQUE !**")
                                            await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant ,damage, add_action_to_log, turn_a)
                                        elif nom_pouvoir_a_activer == "Bombardement":
                                            await add_action_to_log(f"✈️ {nom_attaquant} lance un **Bombardement** !")
                                            if turn_a: team_a_bombardement_stun = True
                                            else: team_b_bombardement_stun = True
                                            cibles_reserve = [p for p in team_defenseur if p['pv'] > 0 and p != defenseur]
                                            if cibles_reserve:
                                                base_bomb_damage = math.ceil(effective_attack * 0.5) * damage_multiplier        
                                                for cible in cibles_reserve:            # On calcule le critique pour chaque cible            
                                                    damage, did_crit = calculate_final_damage(base_bomb_damage, attaquant)            
                                                    crit_msg = " (💥 **Critique !**)" if did_crit else ""            
                                                    cible['pv'] = max(0, cible['pv'] - damage)            
                                                    await add_action_to_log(f"💥 **{cible['nom']}** subit **{damage}** pts de dégâts{crit_msg} !")
                                            else:
                                                await add_action_to_log("...mais la réserve adverse est vide !")
                                        elif nom_pouvoir_a_activer == "Pile ou Face":
                                            await add_action_to_log(f"🎲 {nom_attaquant} utilise **Pile ou Face** !")
                                            if random.choice(['pile', 'face']) == 'face':
                                                base_damage, did_crit = calculate_final_damage(effective_attack, attaquant) 
                                                damage = base_damage * damage_multiplier     
                                                await add_action_to_log(f"🤑 **FACE !** **{effective_attack}** pts de dégâts bruts !")        
                                                if did_crit:            
                                                    await add_action_to_log("💥 **COUP CRITIQUE !**")        
                                                await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant ,damage, add_action_to_log, turn_a)
                                            else:
                                                damage = effective_attack                                               
                                                await add_action_to_log(f"😵 **PILE !** Il subit **{damage}** pts de dégâts bruts.")                                                                                                
                                                # On applique les dégâts à soi-même et on récupère les dégâts réellement subis                                                
                                                damage_taken = await apply_damage(nom_attaquant, attaquant, "Lui-même", attaquant, damage, add_action_to_log, not turn_a)                                                
                                                # On vérifie si la synergie s'active                                                
                                                if damage_taken > 0 and attaquant.get("equipement") and attaquant["equipement"].get("nom") == "Côte épineuse":                                                    
                                                    reflected_damage = math.ceil(damage_taken * 0.5) * damage_multiplier                                                   
                                                    await add_action_to_log(f"💡 La malchance de {nom_attaquant} se retourne contre son adversaire !", delay=0.5)                                                    
                                                    await add_action_to_log(f"🌵 La Côte épineuse renvoie **{reflected_damage}** pts de dégâts à {nom_defenseur} !", delay=0.5)                                                                                                        
                                                    # On applique les dégâts de renvoi à l'adversaire (le vrai défenseur)                                                    
                                                    defenseur['pv'] -= reflected_damage                                                    
                                                    await add_action_to_log(f"🩸 {nom_defenseur} subit les dégâts. (PV restants : {max(0, defenseur['pv'])})")
                                        elif nom_pouvoir_a_activer == "Armure":
                                            await add_action_to_log(f"🛡️ {nom_attaquant} active **Armure** !")
                                            attaquant['armure'] += 3
                                        elif nom_pouvoir_a_activer == "Batteries d'urgences":
                                            await add_action_to_log(f"🔋 {nom_attaquant} active **Batteries d'urgences** !")
                                            soin = math.ceil(attaquant['max_pv'] * 0.25)
                                            await apply_heal(attaquant, soin, "Batteries d'urgences")
                                        elif nom_pouvoir_a_activer == "Nécromancie":
                                            zombie_actuel = zombie_a if turn_a else zombie_b
                                            if not zombie_actuel:
                                                await add_action_to_log(f"💀 {nom_attaquant} active **Nécromancie** !")
                                                zombie_pv = math.ceil(attaquant['max_pv'] * 0.33)
                                                zombie_atk = attaquant['attaque']
                                                nouveau_zombie = {'pv': zombie_pv, 'max_pv': zombie_pv, 'attaque': zombie_atk}
                                                if turn_a: zombie_a = nouveau_zombie
                                                else: zombie_b = nouveau_zombie
                                                await add_action_to_log(f"Un Zombie apparaît avec **{zombie_pv} PV** et **{zombie_atk} d'attaque**.")
                                                await add_action_to_log(f"Le Zombie attaque immédiatement !")
                                                first_strike_damage = random.randint(1, zombie_atk) * damage_multiplier
                                                await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant ,first_strike_damage, add_action_to_log, turn_a)
                                        elif nom_pouvoir_a_activer == "Bénédiction":
                                            soin = math.ceil(attaquant['max_pv'] * 0.20)
                                            await add_action_to_log(f"✨ {nom_attaquant} active **Bénédiction** et soigne tous ses alliés de **{soin}** PV !")
                                            for personnage in team_attaquant:
                                                if personnage['pv'] > 0:
                                                    await apply_heal(personnage, soin, "Bénédiction") 
                                        elif nom_pouvoir_a_activer == "Poison":
                                            await add_action_to_log(f"☠️ {nom_attaquant} active **Poison** !")
                                            defenseur['poison_stacks'] += 1
                                            await add_action_to_log(f"{nom_defenseur} est maintenant empoisonné (Charge: {defenseur['poison_stacks']}) !")
                                            if 'malade' not in defenseur.get('etats', []):                                                
                                                # On utilise .get() pour la sécurité, même si on sait que 'etats' existe.                                                
                                                defenseur['etats'].append('malade')                                                
                                                await add_action_to_log(f"🤒 À cause du poison, {nom_defenseur} est maintenant **Malade** et ne peut plus être soigné !")
                                        elif nom_pouvoir_a_activer == "Elan de puissance":
                                            existing_effect = next((e for e in attaquant['effects'] if e['name'] == 'Élan de puissance'), None)
                                            if existing_effect:
                                                await add_action_to_log(f"⚡ {nom_attaquant} intensifie son **Élan de puissance** !")
                                                existing_effect['value'] += 2
                                                existing_effect['duration'] -= 1
                                            else:
                                                await add_action_to_log(f"💪 {nom_attaquant} active **Élan de puissance** !")
                                                attaquant['effects'].append({'name': 'Élan de puissance', 'type': 'attack_buff', 'value': 5, 'duration': 5})
                                            recalculate_and_update_attack(attaquant)
                                            await add_action_to_log(f"Son attaque passe à **{attaquant['attaque']}** !", delay=0.5)
                                        elif nom_pouvoir_a_activer == "Talon d'Achille":
                                            await add_action_to_log(f"🎯 {nom_attaquant} active **Talon d'Achille** !")
                                            if turn_a: team_a_talon_active = True
                                            else: team_b_talon_active = True
                                            await add_action_to_log("Les prochains dégâts de son équipe perceront toutes les défenses.", delay=0.5)
                                        elif nom_pouvoir_a_activer == "Mimétisme":
                                            if turn_a:
                                                if team_b_last_power:
                                                    await add_action_to_log(f"🌀 {nom_attaquant} active **Mimétisme** et copie **{team_b_last_power}** !")
                                                    await activate_copied_power(team_b_last_power, attaquant, defenseur, turn_a, nom_attaquant, nom_defenseur )
                                                else:
                                                    await add_action_to_log(f"🌀 {nom_attaquant} active **Mimétisme**, mais ne trouve rien à copier...")
                                            else:
                                                if team_a_last_power:
                                                    await add_action_to_log(f"🌀 {nom_attaquant} active **Mimétisme** et copie **{team_a_last_power}** !")
                                                    await activate_copied_power(team_a_last_power, attaquant, defenseur, turn_a,nom_attaquant, nom_defenseur)
                                                else:
                                                    await add_action_to_log(f"🌀 {nom_attaquant} active **Mimétisme**, mais ne trouve rien à copier...")
                                        elif nom_pouvoir_a_activer == "Roboréparation":        
                                            soin = 30 # Soin fixe        
                                            await add_action_to_log(f"🔧 {nom_attaquant} active **Roboréparation** !")        
                                            await apply_heal(attaquant, soin, "Roboréparation")
                                        elif nom_pouvoir_a_activer == "Changement tactique":                                            
                                            # On cherche les alliés vivants sur le banc                                            
                                            allies_banc_vivants = [p for p in team_attaquant if p['pv'] > 0 and p != attaquant]                                            
                                            if allies_banc_vivants:                                                
                                                # On trouve celui avec le plus de PV                                                
                                                cible_swap = max(allies_banc_vivants, key=lambda p: p['pv'])                                                
                                                await add_action_to_log(f"⚙️ {nom_attaquant} active **Changement tactique** et échange sa place avec **{cible_swap['nom']}** !")                                                                                                
                                                # On gère les effets de sortie et d'entrée                                                
                                                await handle_character_swap_out(attaquant)                                                
                                                if turn_a: active_a = cible_swap                                                
                                                else: active_b = cible_swap                                                
                                                attaquant = cible_swap # Le nouvel attaquant est la cible du swap                                                
                                                await handle_character_swap_in(attaquant,defenseur)                                            
                                            else:                                                
                                                await add_action_to_log(f"⚙️ {nom_attaquant} tente d'utiliser **Changement tactique**, mais n'a aucun allié sur le banc !")
                                        elif nom_pouvoir_a_activer == "Catalyseur":        
                                            await add_action_to_log(f"🔬 {nom_attaquant} active **Catalyseur** !")        
                                            if turn_a:            
                                                catalyseur_bonus_a = 0.10        
                                            else:            
                                                catalyseur_bonus_b = 0.10        
                                            await add_action_to_log("Les chances de changement automatique de son équipe augmentent pour ce tour !")
                                             # ... (après la logique de "Catalyseur" que vous venez d'ajouter)

                                        elif nom_pouvoir_a_activer == "Robots expérimentaux":
                                            await add_action_to_log(f"🤖 {nom_attaquant} active **Robots expérimentaux** !")
                                            if len(team_attaquant) < 3:
                                                # On récupère le modèle du robot depuis le catalogue des ennemis
                                                robot_model = self.bot.catalogue_ennemis.get("Robot expérimental")
                                                if robot_model:
                                                    nouveau_robot = copy.deepcopy(robot_model)
                                                    
                                                    # --- Initialisation cruciale du nouveau personnage ---
                                                    nouveau_robot['max_pv'] = nouveau_robot['pv']
                                                    nouveau_robot['base_attaque'] = nouveau_robot['attaque']
                                                    nouveau_robot['effects'] = []
                                                    nouveau_robot['poison_stacks'] = 0
                                                    nouveau_robot['etats'] = []
                                                    nouveau_robot['bonus_degats'] = 0
                                                    nouveau_robot['couronne_active'] = False
                                                    nouveau_robot['bandeau_used_this_stint'] = False
                                                    nouveau_robot['pv_at_turn_end'] = nouveau_robot['pv']
                                                    if 'armure' not in nouveau_robot: nouveau_robot['armure'] = 0
                                                    # --- Fin de l'initialisation ---

                                                    team_attaquant.append(nouveau_robot)
                                                    await add_action_to_log(f"Un **Robot expérimental** rejoint le combat aux côtés de {nom_attaquant} !")
                                                else:
                                                    await add_action_to_log("...mais le modèle du robot est introuvable !")
                                            else:
                                                await add_action_to_log("...mais son équipe est déjà au complet !")
                                        elif nom_pouvoir_a_activer == "Robots expérimentaux noirs":                                            
                                            await add_action_to_log(f"⚫ {nom_attaquant} active **Robots expérimentaux noirs** !")                                            
                                            if len(team_attaquant) < 3:                                                
                                                robot_model = self.bot.catalogue_ennemis.get("Robot expérimental noir")                                                
                                                if robot_model:                                                    
                                                    nouveau_robot = copy.deepcopy(robot_model)                                                                                                        
                                                    # Initialisation complète du nouveau personnage                                                    
                                                    nouveau_robot['max_pv'] = nouveau_robot['pv']                                                    
                                                    nouveau_robot['base_attaque'] = nouveau_robot['attaque']                                                    
                                                    nouveau_robot['effects'] = []                                                    
                                                    nouveau_robot['poison_stacks'] = 0                                                    
                                                    nouveau_robot['etats'] = []                                                    
                                                    nouveau_robot['bonus_degats'] = 0                                                    
                                                    nouveau_robot['couronne_active'] = False                                                    
                                                    nouveau_robot['bandeau_used_this_stint'] = False                                                    
                                                    nouveau_robot['pv_at_turn_end'] = nouveau_robot['pv']                                                    
                                                    if 'armure' not in nouveau_robot: nouveau_robot['armure'] = 0                                                                                                        
                                                    team_attaquant.append(nouveau_robot)                                                    
                                                    await add_action_to_log(f"Un **Robot expérimental noir** rejoint le combat !")                                                
                                                else:                                                    
                                                        await add_action_to_log("...mais le modèle du robot noir est introuvable !")                                            
                                            else:                                                
                                                await add_action_to_log("...mais son équipe est déjà au complet !")
                                        # ... (avant `elif nom_pouvoir_a_activer == "Roboréparation":`)
                                    
                                    
                                            
                                        if turn_a: team_a_last_power = nom_pouvoir_a_activer
                                        else: team_b_last_power = nom_pouvoir_a_activer
                                        pouvoirs_actives_ce_tour += 1

                        if not is_parieur_ability_turn:  
                                if effective_attack > 0:                                                  
                                    base_damage = 0                                
                                    if attaquant.get('couronne_active', False):                                    
                                        await add_action_to_log(f"👑 L'attaque du survivant est **brute** et prévisible !")                                    
                                        base_damage = effective_attack * damage_multiplier                                
                                    else:                                    
                                        base_damage = await async_roll_for_damage(attaquant, 1, effective_attack) * damage_multiplier
                                    raw_damage, did_crit = calculate_final_damage(base_damage, attaquant)   
                                    await add_action_to_log(f"💥 {nom_attaquant} attaque avec une puissance de **{base_damage}** !")    
                                    if did_crit:        
                                        await add_action_to_log("💥 **COUP CRITIQUE !** Les dégâts sont massivement augmentés !")
                                    if raw_damage > 0:
                                        await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant, raw_damage, add_action_to_log, turn_a)   
                                    if attaquant.get('capacite_unique') == "Rage interne" and attaquant['pv'] < (attaquant['max_pv'] / 2) and defenseur['pv'] > 0:                        
                                        await add_action_to_log(f"💢 **Rage interne !** {nom_attaquant} est enragé et attaque à nouveau !", delay=1)                                                
                                        # On copie la logique d'une attaque de base                        
                                        base_damage_rage = await async_roll_for_damage(attaquant, 1, effective_attack) * damage_multiplier                        
                                        raw_damage_rage, did_crit_rage = calculate_final_damage(base_damage_rage, attaquant)                                                
                                        await add_action_to_log(f"💥 {nom_attaquant} attaque avec une puissance de **{base_damage_rage}** !")                        
                                        if did_crit_rage:                            
                                            await add_action_to_log("💥 **COUP CRITIQUE !** Les dégâts sont massivement augmentés !")                                                
                                        if raw_damage_rage > 0:                            
                                            await apply_damage(nom_defenseur, defenseur, nom_attaquant, attaquant, raw_damage_rage, add_action_to_log, turn_a)
                                else:
                                    await add_action_to_log(f"🌀 {nom_attaquant} est passif et n'attaque pas.")                                                        
                                if attaquant.get('nom') == "Le Parieur": attaquant['parieur_ability_ready'] = True

                        if (defenseur.get('nom') == "Le Robot" and not defenseur.get('ability_used_this_stint', False) and defenseur['pv'] > 0 and defenseur['pv'] < defenseur['max_pv'] / 2):
                            defenseur['ability_used_this_stint'] = True
                            defenseur['repair_mode_active'] = True
                            defenseur['repair_turns_left'] = 3
                            await add_action_to_log(f"⚠️ {nom_defenseur} active son protocole de réparation !")

                if defenseur['pv'] <= 0:
                    defenseur['pv'] = 0
                    await add_action_to_log(f"☠️ {nom_defenseur} est hors de combat !")
                    ancien_defenseur = defenseur
                    await handle_death_effects(mort=ancien_defenseur, team_mort=team_defenseur, attaquant=attaquant, team_attaquant=team_attaquant, tour_actif_a=turn_a)
                    await remove_grimoire_buff(ancien_defenseur)
                    await remove_baguette_buff(ancien_defenseur)
                    
                    prochain_combattant = next((p for p in team_defenseur if p['pv'] > 0), None)
                    if not prochain_combattant:                        
                        winner_name = nom_joueur if turn_a else nom_adversaire                        
                        return await _handle_victory(winner_name, team_a, team_b, is_pve)
                    else:
                        if turn_a: active_b = prochain_combattant
                        else: active_a = prochain_combattant
                        defenseur = prochain_combattant
                        await handle_character_swap_in(prochain_combattant, attaquant)
                        await add_action_to_log(f"▶️ {('**' if not turn_a else nom_adversaire + ' **')}{prochain_combattant['nom']}** entre en scène !")
                            # ... le code de votre tour se termine juste avant ceci (après la gestion de la mort du défenseur)

                            # ===================================================================
                # =================== GESTION FINALE DU TOUR (FINALE) ===============
                # ===================================================================
                # On mémorise les PV de l'attaquant actuel pour sa prochaine vérification.
                attaquant['pv_at_turn_end'] = attaquant['pv']

                if turn_a:
                    # Le tour de l'équipe A se termine
                    if tempo_pending_a:
                        await add_action_to_log(f"⚡ **Tempo** s'active ! {nom_attaquant} rejoue son tour !")
                        tempo_pending_a = False
                        is_bonus_turn_a = True
                        # On ne change pas de joueur
                    else:
                        turn_a = not turn_a # On passe à l'équipe B
                else:
                    # Le tour de l'équipe B se termine
                    if tempo_pending_b:
                        await add_action_to_log(f"⚡ **Tempo** s'active ! {nom_attaquant} rejoue son tour !")
                        tempo_pending_b = False
                        is_bonus_turn_b = True
                        # On ne change pas de joueur
                    else:
                        turn_a = not turn_a # On passe à l'équipe A

                update_embed_fields()
                await log_message.edit(embed=embed)


                for p in team_a + team_b:                    
                    if 'bandeau_invincible' in p.get('etats', []):                        
                        p['etats'].remove('bandeau_invincible')                        
                        nom_perso_formate = f"**{p['nom']}**"                        
                        # On met un délai à 0 pour que ce message apparaisse en même temps que la fin du tour.                        
                        await add_action_to_log(f"🎗️ La protection du Bandeau rouge s'estompe pour {nom_perso_formate}.", delay=0)
                # ===================================================================

                            # ... (code de la gestion de Tempo) ...

                ### AJOUTEZ CE BLOC DE SAUVEGARDE ###
                # On rassemble toutes les variables importantes dans un dictionnaire
                combat_variables = {
                    'team_a_last_power': team_a_last_power, 'team_b_last_power': team_b_last_power,
                    'team_a_poulets': team_a_poulets, 'team_b_poulets': team_b_poulets,
                    'team_a_talon_active': team_a_talon_active, 'team_b_talon_active': team_b_talon_active,
                    'team_a_is_stunned': team_a_is_stunned, 'team_b_is_stunned': team_b_is_stunned,
                    'team_a_peur_bleu': team_a_peur_bleu, 'team_b_peur_bleu': team_b_peur_bleu,
                    'prescience_timer_a': prescience_timer_a, 'prescience_timer_b': prescience_timer_b,
                    'prescience_damage_multiplier_a': prescience_damage_multiplier_a, 'prescience_damage_multiplier_b': prescience_damage_multiplier_b,
                    'prescience_caster_a': prescience_caster_a, 'prescience_caster_b': prescience_caster_b,
                    'team_a_bouclier_magique': team_a_bouclier_magique, 'team_b_bouclier_magique': team_b_bouclier_magique,
                    'bouclier_magique_expire_a': bouclier_magique_expire_a, 'bouclier_magique_expire_b': bouclier_magique_expire_b,
                    'team_a_bombardement_stun': team_a_bombardement_stun, 'team_b_bombardement_stun': team_b_bombardement_stun,
                    'zombie_a': zombie_a, 'zombie_b': zombie_b,
                    'turn_a': turn_a, 'tour_count': tour_count, 'combat_log': combat_log[-20:], # On ne garde que les 20 derniers logs
                    'tempo_pending_a': tempo_pending_a, 'tempo_pending_b': tempo_pending_b,
                    'is_bonus_turn_a': is_bonus_turn_a, 'is_bonus_turn_b': is_bonus_turn_b
                }

        
                current_state = {
                    'channel_id': log_message.channel.id,
                    'message_id': log_message.id,
                    'team_a': team_a,
                    'team_b': team_b,
                    'titre_combat': titre_combat,
                    'nom_adversaire': nom_adversaire,
                    'active_a_nom': active_a['nom'],
                    'active_b_nom': active_b['nom'],
                    'variables': combat_variables
                }
                self._save_combat_state(log_message.channel.id, current_state)

                update_embed_fields()
                await log_message.edit(embed=embed)

        # DANS cogs/combat.py -> lancer_combat_engine

        # --- DÉBUT DE LA MODIFICATION ---
        except (asyncio.TimeoutError, discord.errors.HTTPException, aiohttp.client_exceptions.ClientOSError) as e:
            # Ces erreurs sont typiques d'une déconnexion.
            # On les signale dans la console, mais on ne fait RIEN d'autre.
            # On ne supprime PAS la sauvegarde et on ne met PAS fin au combat.
            # On laisse la bibliothèque discord.py gérer la reconnexion.
            print(f"Erreur de réseau ou de l'API Discord détectée (normal en cas de coupure) : {e}")
            print("Le bot va tenter de se reconnecter. Le combat est en pause.")
            # La boucle est interrompue, mais la fonction ne se termine pas,
            # et surtout, elle ne retourne pas `None`. Le système de reprise `on_ready`
            # pourra prendre le relais si le script venait à crasher complètement.
            
        except Exception as e:
            # Ceci attrape TOUTES les autres erreurs (erreurs de code, etc.)
            # Pour CELLES-CI, on veut arrêter le combat.
            print(f"Une erreur inattendue et critique a mis fin au combat : {e}")
            import traceback
            traceback.print_exc() # Imprime des détails très utiles pour le débogage
            
            # On vérifie que log_message n'est pas None avant de l'utiliser
            if log_message:
                self._delete_combat_state(log_message.channel.id)
                embed.description = f"❌ **ERREUR CRITIQUE** ❌\nLe combat a été interrompu en raison d'une erreur interne.\n`{e}`"
                try:
                    await log_message.edit(embed=embed)
                except discord.errors.HTTPException:
                    pass # On ne peut pas modifier le message si on est déconnecté
        # --- FIN DE LA MODIFICATION ---


# ...   
            

        update_embed_fields()
        final_log_lines = []    
        current_length = 0
        char_limit = 4096 - 100
        for entry in reversed(combat_log):
            if current_length + len(entry) + 1 > char_limit: break
            final_log_lines.insert(0, entry)
            current_length += len(entry) + 1
        final_log_display = "\n".join(final_log_lines)
        if len(final_log_lines) < len(combat_log): final_log_display = f"_(Affichage des dernières actions du combat...)_\n\n" + final_log_display
        embed.description = final_log_display
        await log_message.edit(embed=embed)


    @app_commands.command(name="combat_test", description="Lance un combat test de votre réserve contre un clone.")
    async def combat_test(self, interaction: discord.Interaction):
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        if any(p is None for p in user_inv["reserve_combat"]):
                return await interaction.response.send_message("Votre réserve de combat doit être complète.", ephemeral=True)

        team_a = copy.deepcopy(user_inv["reserve_combat"])
        team_b = copy.deepcopy(user_inv["reserve_combat"])
        nom_joueur = interaction.user.name
        titre_combat = "Combat Test"
        nom_adversaire = "Clone"

        # Étape 1: Envoyer le message initial
        embed = discord.Embed(title=f"⚔️ {titre_combat} en cours... ⚔️", description="Le combat va commencer !", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)
        log_message = await interaction.original_response()

            # Étape 2: Lancer le moteur en tâche de fond
        asyncio.create_task(self.lancer_combat_engine(
                log_message=log_message,
                team_a=team_a,
                team_b=team_b,
                titre_combat=titre_combat,
                nom_joueur=nom_joueur,
                nom_adversaire=nom_adversaire
            ))

    @app_commands.command(name="combat_test_aleatoire", description="Lance un combat contre une équipe aléatoire.")
    async def combat_test_aleatoire(self, interaction: discord.Interaction):
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        if any(p is None for p in user_inv["reserve_combat"]):
            return await interaction.response.send_message("Votre réserve de combat doit être complète.", ephemeral=True)
        
        team_a = copy.deepcopy(user_inv["reserve_combat"])
        team_b = self._creer_equipe_aleatoire()
        
        if not team_b:
            return await interaction.response.send_message("Pas assez de personnages dans le catalogue pour créer une équipe adverse.", ephemeral=True)

        nom_joueur = interaction.user.name
        titre_combat = "Combat Aléatoire"
        nom_adversaire = "Bot"

        # Étape 1: Envoyer le message initial
        embed = discord.Embed(title=f"⚔️ {titre_combat} en cours... ⚔️", description="Le combat va commencer !", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)
        log_message = await interaction.original_response()

        # Étape 2: Lancer le moteur en tâche de fond
        asyncio.create_task(self.lancer_combat_engine(
            log_message=log_message,
            team_a=team_a,
            team_b=team_b,
            titre_combat=titre_combat,
            nom_joueur=nom_joueur,
            nom_adversaire=nom_adversaire
        ))

    @app_commands.command(name="combat_admin", description="[ADMIN] Lance un combat contre une équipe de bot personnalisée.")
    @app_commands.autocomplete(perso_bot_1=catalogue_personnage_autocompletion, perso_bot_2=catalogue_personnage_autocompletion, perso_bot_3=catalogue_personnage_autocompletion)
    async def combat_admin(self, interaction: discord.Interaction, perso_bot_1: str, perso_bot_2: str, perso_bot_3: str):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Commande réservée.", ephemeral=True)
        
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        if any(p is None for p in user_inv["reserve_combat"]):
            return await interaction.response.send_message("Votre réserve de combat doit être complète.", ephemeral=True)
        
        team_a = copy.deepcopy(user_inv["reserve_combat"])
        team_b = []
        bot_team_names = [perso_bot_1, perso_bot_2, perso_bot_3]
        for nom in bot_team_names:
            perso_catalogue = self.bot.catalogue_personnages.get(nom)
            if not perso_catalogue:
                return await interaction.response.send_message(f"Erreur : Personnage '{nom}' introuvable.", ephemeral=True)
            team_b.append(copy.deepcopy(perso_catalogue))

        nom_joueur = interaction.user.name
        titre_combat = "Combat Admin"
        nom_adversaire = "Bot"

        # Étape 1: Envoyer le message initial
        embed = discord.Embed(title=f"⚔️ {titre_combat} en cours... ⚔️", description="Le combat va commencer !", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)
        log_message = await interaction.original_response()

        # Étape 2: Lancer le moteur en tâche de fond
        asyncio.create_task(self.lancer_combat_engine(
            log_message=log_message,
            team_a=team_a,
            team_b=team_b,
            titre_combat=titre_combat,
            nom_joueur=nom_joueur,
            nom_adversaire=nom_adversaire
        ))

    @app_commands.command(name="combat_bots", description="Lance un combat de démonstration entre deux équipes aléatoires.")
    async def combat_bots(self, interaction: discord.Interaction):
        team_a = self._creer_equipe_aleatoire()
        team_b = self._creer_equipe_aleatoire()

        if not team_a or not team_b:
            return await interaction.response.send_message("Pas assez de personnages dans le catalogue pour créer deux équipes complètes.", ephemeral=True)

        titre_combat = "Combat de Bots"
        nom_joueur = "Équipe Alpha"
        nom_adversaire = "Équipe Oméga"

        # Étape 1: Envoyer le message initial
        embed = discord.Embed(title=f"⚔️ {titre_combat} en cours... ⚔️", description="Le combat va commencer !", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)
        log_message = await interaction.original_response()

        # Étape 2: Lancer le moteur en tâche de fond
        asyncio.create_task(self.lancer_combat_engine(
            log_message=log_message,
            team_a=team_a,
            team_b=team_b,
            titre_combat=titre_combat,
            nom_joueur=nom_joueur,
            nom_adversaire=nom_adversaire
        ))

async def setup(bot: commands.Bot):
    await bot.add_cog(CombatCog(bot))