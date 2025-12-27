# cogs/combat_engine_1v1.py

import discord
import asyncio
import random

class CombatEngine:
    # Dans la classe CombatEngine de cogs/combat_engine_1v1.py
    
    # Dans la classe CombatEngine de cogs/combat_engine_1v1.p

    def _execute_attack(self, attacker_state, defender_state, i):
        """Exécute une attaque entre deux personnages, en prenant en compte les statuts."""
        attacker_char = attacker_state['terrain']
        defender_char = defender_state['terrain']

        if not attacker_char:            
            self.log.append(f"💨 {attacker_state['member'].display_name} n'a pas de personnage et passe son tour.")            
            return # On arrête la fonction ici
        
        
        damage = attacker_char['attaque']

        if defender_char and "Sommeil" in defender_char.get("statuts", []):
            self.log.append(f"💤 **{defender_char['nom']}** est en Sommeil et ne peut pas être attaqué.")
            return
        
        if defender_char and "Contre" in defender_char.get("statuts", []):        
            self.log.append(f"⚔️ **{defender_char['nom']}** contre l'attaque de **{attacker_char['nom']}** !")        
            # Appliquer les dégâts à l'attaquant au lieu du défenseur        
            attacker_char['pv'] -= damage        
            self.log.append(f"💔 **{attacker_char['nom']}** subit **{damage}** points de dégâts de sa propre attaque ! (PV restants : {max(0, attacker_char['pv'])})")                
            # Vérifier si l'attaquant est vaincu par sa propre attaque        
            if attacker_char['pv'] <= 0:     
                if 'volonte' in attacker_state.get('passives', {}) and "Volonté" in attacker_char.get("statuts", []):                    
                    attacker_char['pv'] = 1  # Le personnage survit avec 1 PV                    
                    attacker_char["statuts"].remove("Volonté") # L'effet est consommé                    
                    self.log.append(f"💎 La **Volonté** de **{attacker_char['nom']}** lui permet de survivre avec 1 PV !")                    
                    return        
                self.log.append(f"☠️ **{attacker_char['nom']}** a été vaincu par sa propre attaque !")
                if "Calin" in attacker_char.get("statuts", []) and defender_char:        
                    if "statuts" not in defender_char:                        
                        defender_char["statuts"] = []   
                    if "Envoûté" not in defender_char["statuts"]:            
                        defender_char["statuts"].append("Envoûté")            
                        # Réduire l'attaque à 1            
                        defender_char["attaque_originale"] = defender_char["attaque"]            
                        defender_char["attaque"] = 1            
                        self.log.append(f"👻 **{attacker_char['nom']}** envoûte **{defender_char['nom']}** en mourant ! Son attaque est réduite à 1.")           
                if "Recherché" in attacker_char.get("statuts", []):                
                    defender_state['pr'] += 2                
                    self.log.append(f"💰 **{defender_state['member'].display_name}** récupère 2 PR grâce à la prime !")            
                    attacker_state['terrain'] = None            
                if "Cape Guerrière" in attacker_char.get("statuts", []):                
                        self.log.append(f"🧥 **Cape Guerrière** est détruite avec **{attacker_char['nom']}** !")                
                        attacker_char["statuts"].remove("Cape Guerrière")                
            return  # Important: sortir de la méthode après le contre
        
        if defender_char and "Garde du corps" in defender_char.get("statuts", []):    
            # Récupérer le nombre de gardes    
            nb_gardes = defender_char.get("nb_gardes", 1)        
            if nb_gardes > 0:        
                # Réduire le nombre de gardes        
                defender_char["nb_gardes"] = nb_gardes - 1                
                # Si c'était le dernier garde, retirer le statut        
                if defender_char["nb_gardes"] == 0:            
                    defender_char["statuts"].remove("Garde du corps")                
                self.log.append(f"💂 Un garde du corps protège **{defender_char['nom']}** de l'attaque ! ({defender_char.get('nb_gardes', 0)} gardes restants)")        
                return  # Sortir de la méthode, l'attaque est bloquée

        if defender_char and "Coton" in defender_char.get("statuts", []):
            self.log.append(f"🛡️ **{defender_char['nom']}** est protégé par le Bouclier Coton !")
            damage = min(damage, 1)
        surprise_bonus = 1  # Multiplicateur par défaut
        if "À l'affût" in attacker_char.get("statuts", []):
            if i == 0:
                surprise_bonus = 2
                self.log.append(f"🦊 **{attacker_char['nom']}** lance une Attaque Surprise !")
        damage = damage * surprise_bonus

        attacker_floats = "statuts" in attacker_char and "Flotte" in attacker_char["statuts"]
        defender_floats = defender_char and "statuts" in defender_char and "Flotte" in defender_char["statuts"]
        attacker_flies = "statuts" in attacker_char and "Vol" in attacker_char["statuts"]
        
        target_is_player = False
        if not defender_char:
            target_is_player = True
            self.log.append(f"⚔️ **{attacker_char['nom']}** attaque directement les HP de **{defender_state['member'].display_name}** !")
        elif defender_floats and not attacker_floats:
            target_is_player = True
            self.log.append(f"☁️ Le personnage de **{defender_state['member'].display_name}** flotte ! L'attaque vise directement ses HP !")
        elif attacker_flies:  
            # NOUVEAU    
            target_is_player = True    
            self.log.append(f"🐝 **{attacker_char['nom']}** vole au-dessus du terrain et attaque directement les HP de **{defender_state['member'].display_name}** !")
        else:
            self.log.append(f"💥 **{attacker_char['nom']}** attaque **{defender_char['nom']}** !")

        if target_is_player:
            defender_state['hp'] -= damage
            self.log.append(f"❤️ Il subit **{damage}** points de dégâts !")
            
            if defender_state.get('parapluie_active'):            
                defender_state['pr'] += damage            
                self.log.append(f"☔ Les {damage} dégâts sont convertis en PR pour {defender_state['member'].display_name} (Parapluie).")
        else:
            defender_char['pv'] -= damage
            self.log.append(f"💔 Il subit **{damage}** points de dégâts ! (PV restants : {max(0, defender_char['pv'])})")
            
            if defender_state.get('parapluie_active'):            
                defender_state['pr'] += damage            
                self.log.append(f"☔ Les {damage} dégâts subis par **{defender_char['nom']}** sont convertis en PR pour {defender_state['member'].display_name} (Parapluie).")

            if defender_char['pv'] <= 0:
                if 'volonte' in defender_state.get('passives', {}) and "Volonté" in defender_char.get("statuts", []):                    
                    defender_char['pv'] = 1  # Le personnage survit avec 1 PV                    
                    defender_char["statuts"].remove("Volonté") # L'effet est consommé                    
                    self.log.append(f"💎 La **Volonté** de **{defender_char['nom']}** lui permet de survivre avec 1 PV !")                    
                    return 
                self.log.append(f"☠️ **{defender_char['nom']}** a été vaincu !")
                if "Calin" in defender_char.get("statuts", []) and attacker_char:        
                    if "statuts" not in attacker_char:                        
                        attacker_char["statuts"] = []    
                    if "Envoûté" not in attacker_char["statuts"]:            
                        attacker_char["statuts"].append("Envoûté")            
                        # Réduire l'attaque à 1            
                        attacker_char["attaque_originale"] = attacker_char["attaque"]            
                        attacker_char["attaque"] = 1            
                        self.log.append(f"👻 **{defender_char['nom']}** envoûte **{attacker_char['nom']}** en mourant ! Son attaque est réduite à 1.")
                if "Recherché" in defender_char.get("statuts", []):
                    attacker_state['pr'] += 2
                    self.log.append(f"💰 **{attacker_state['member'].display_name}** récupère 2 PR grâce à la prime !")
                defender_state['terrain'] = None
                if "Cape Guerrière" in defender_char.get("statuts", []):                
                    self.log.append(f"🧥 **Cape Guerrière** est détruite avec **{defender_char['nom']}** !")                
                    defender_char["statuts"].remove("Cape Guerrière")

        # Logique de soin pour "Art contemporain"
        if "Art contemporain" in attacker_char.get("statuts", []):
            heal_amount = damage
            attacker_state['hp'] = min(50, attacker_state['hp'] + heal_amount)
            self.log.append(f"🖼️ **{attacker_char['nom']}** soigne son maître de **{heal_amount}** HP !")

    async def _send_post_combat_report(self, player_state, opponent_state):
        """Envoie un rapport au joueur sur l'état de l'adversaire à la fin du combat."""
        
        
        if player_state.get('is_ai'):        
            return
        
        # Construire la description de l'inventaire de l'adversaire
        
        
        opponent_inventory_desc = []
        for i, char in enumerate(opponent_state['inventaire']):
            if char:
                opponent_inventory_desc.append(f"Slot {i+1}: **{char['nom']}**")
            else:
                opponent_inventory_desc.append(f"Slot {i+1}: Vide")
        
        # Gérer le terrain de l'adversaire
        if opponent_state['terrain']:
            opponent_terrain_desc = f"**{opponent_state['terrain']['nom']}**"
        else:
            opponent_terrain_desc = "Aucun"

        embed = discord.Embed(
            title=f"Rapport de Fin de Tour {self.game_state['tour']}",
            description=f"Voici l'état du jeu de votre adversaire, **{opponent_state['member'].display_name}**, avant cette nouvelle phase de préparation.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Son Terrain", value=opponent_terrain_desc, inline=False)
        embed.add_field(name="Son Inventaire", value="\n".join(opponent_inventory_desc), inline=False)
    
        try:
            dm_channel = player_state['member'].dm_channel or await player_state['member'].create_dm()
            await dm_channel.send(embed=embed)
        except discord.Forbidden:
            # Le joueur a peut-être bloqué le bot ou fermé ses MPs
            pass

    def __init__(self, manager_cog, game_state):
        self.manager = manager_cog
        self.bot = manager_cog.bot
        self.game_state = game_state
        self.log = []

        # Pré-assigner les variables pour un accès plus facile
        player_ids = list(self.game_state['players'].keys())
        self.p1_id, self.p2_id = player_ids[0], player_ids[1]
        self.p1_state = self.game_state['players'][self.p1_id]
        self.p2_state = self.game_state['players'][self.p2_id]
        self.channel = self.bot.get_channel(game_state['channel_id'])

    def _determine_base_attack_order(self):
        
        char1 = self.p1_state['terrain']        
        char2 = self.p2_state['terrain']       
        # NOUVEAU : Vérification de la capacité "Attaque surprise"        
        p1_has_surprise = char1 and "À l'affût" in char1.get("statuts", [])        
        p2_has_surprise = char2 and "À l'affût" in char2.get("statuts", [])        
        
        if p1_has_surprise and not p2_has_surprise:            
            return [self.p1_id, self.p2_id]        
        if p2_has_surprise and not p1_has_surprise:            
            return [self.p2_id, self.p1_id]
        """Détermine qui attaque en premier selon les règles spécifiées."""
        
        # Règle 1: HP du joueur (le plus bas commence)
        if self.p1_state['hp'] < self.p2_state['hp']: return [self.p1_id, self.p2_id]
        if self.p2_state['hp'] < self.p1_state['hp']: return [self.p2_id, self.p1_id]

        # Règle 2: PR du joueur (le plus haut commence)
        if self.p1_state['pr'] > self.p2_state['pr']: return [self.p1_id, self.p2_id]
        if self.p2_state['pr'] > self.p1_state['pr']: return [self.p2_id, self.p1_id]

        # Règle 3: PV du personnage sur le terrain (le plus bas commence)
        # float('inf') est utilisé si un joueur n'a pas de personnage, pour qu'il soit considéré comme ayant plus de PV
        char1_pv = self.p1_state['terrain']['pv'] if self.p1_state['terrain'] else float('inf')
        char2_pv = self.p2_state['terrain']['pv'] if self.p2_state['terrain'] else float('inf')
        if char1_pv < char2_pv: return [self.p1_id, self.p2_id]
        if char2_pv < char1_pv: return [self.p2_id, self.p1_id]

        # Règle 4: Hasard
        return random.sample([self.p1_id, self.p2_id], 2)
    
        # Dans cogs/combat_engine_1v1.py, classe CombatEngine

    def _determine_attack_order(self):
        """Détermine l'ordre d'attaque en tenant compte du passif 'Vif'."""
        p1_has_vif = 'vif' in self.p1_state.get('passives', {})
        p2_has_vif = 'vif' in self.p2_state.get('passives', {})

        # Si un seul joueur a le passif, il a l'initiative
        if p1_has_vif and not p2_has_vif:
            return ([self.p1_id, self.p2_id], "passif")
        
        if p2_has_vif and not p1_has_vif:
            return ([self.p2_id, self.p1_id], "passif")
            
        # Si les deux l'ont, ou si aucun ne l'a, on utilise la logique de base
        return (self._determine_base_attack_order(), "base")
    

    # Dans la classe CombatEngine de cogs/combat_engine_1v1.py

    def _create_combat_embed(self, title):
        """Crée et met à jour l'embed affichant l'état du combat."""
        embed = discord.Embed(title=f"Tour {self.game_state['tour']} - Phase de Combat", description=title, color=discord.Color.red())
        
        # Dictionnaire pour associer un statut à un emoji
        STATUS_EMOJIS = {
            "Flotte": "☁️",
            "En chasse": "🎯",            
            "Recherché": "📜",
            "À l'affût": "🦊",
            "Incantation": "🔥",
            "Sommeil": "💤",
            "Coton": "🛡️",
            "Art abstrait": "🎨",                       
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
            "À main nue": "👊",
            "Volonté" : "💎"
        }

        # --- Traitement pour le Joueur 1 ---
        p1_char = self.p1_state['terrain']
        p1_info = f"❤️ **HP Joueur**: {self.p1_state['hp']}/50\n"
        if p1_char:
            # Ligne principale avec PV et ATTAQUE
            p1_info += f"**{p1_char['nom']}**: {p1_char['pv']}/{p1_char['pv_max']} PV | ⚔️ {p1_char['attaque']} ATQ"
        
            # Affichage des statuts
            if p1_char.get("statuts"):                    
                status_display = []
                for s in p1_char["statuts"]:
                    if s == "Garde du corps":
                        # Afficher le nombre de gardes
                        nb_gardes = p1_char.get("nb_gardes", 1)
                        status_display.append(f'{STATUS_EMOJIS.get(s, "❓")} {s} ({nb_gardes})')
                    else:
                        status_display.append(f'{STATUS_EMOJIS.get(s, "❓")} {s}')
                p1_info += f"\n*Statuts: {' '.join(status_display)}*"
        else:
            p1_info += "Aucun personnage sur le terrain."
            
        embed.add_field(name=self.p1_state['member'].display_name, value=p1_info, inline=True)

        # --- Traitement pour le Joueur 2 ---
        p2_char = self.p2_state['terrain']
        p2_info = f"❤️ **HP Joueur**: {self.p2_state['hp']}/50\n"
        if p2_char:
            # Ligne principale avec PV et ATTAQUE
            p2_info += f"**{p2_char['nom']}**: {p2_char['pv']}/{p2_char['pv_max']} PV | ⚔️ {p2_char['attaque']} ATQ"
            
            # Ligne pour les statuts
            if p2_char.get("statuts"):                    
                status_display = []
                for s in p2_char["statuts"]:
                    if s == "Garde du corps":
                        # Afficher le nombre de gardes
                        nb_gardes = p2_char.get("nb_gardes", 1)
                        status_display.append(f'{STATUS_EMOJIS.get(s, "❓")} {s} ({nb_gardes})')
                    else:
                        status_display.append(f'{STATUS_EMOJIS.get(s, "❓")} {s}')
                p2_info += f"\n*Statuts: {' '.join(status_display)}*"
        else:
            p2_info += "Aucun personnage sur le terrain."
            
        embed.add_field(name=self.p2_state['member'].display_name, value=p2_info, inline=True)
        
        if self.log:
            # On ne prend que les 12 dernières entrées pour éviter de dépasser la limite de Discord
            log_display = self.log[-12:]
            embed.add_field(name="Déroulement du Combat", value="\n".join(log_display), inline=False)
            
        return embed

    async def run_combat(self):
        """Exécute la séquence complète d'un round de combat."""
        char1 = self.p1_state['terrain']
        char2 = self.p2_state['terrain']
        
        for p_state in [self.p1_state, self.p2_state]:            
            if 'volonte' in p_state.get('passives', {}):                
                # Appliquer aux personnages sur le terrain                
                for char in [p_state.get('terrain')]:                    
                    if char:                        
                        if "statuts" not in char:                            
                            char["statuts"] = []                        
                            # On ajoute le statut seulement s'il n'y est pas déjà                        
                        if "Volonté" not in char["statuts"]:                            
                            char["statuts"].append("Volonté")
        
        
        # Cas particulier : aucun des deux joueurs n'a de personnage sur le terrain
        if not char1 and not char2:
            await self.channel.send("Aucun personnage sur le terrain. Le combat n'a pas lieu pour ce tour.")
            await asyncio.sleep(3)
            await self._end_combat_phase()
            return
        # Vérifier et appliquer le statut "Cadeau de Noël" (Sapin de Noë
                      
        monologue_active = False
        monologue_owner = None

        if char1 and "blablabla" in char1.get("statuts", []):
            monologue_active = True
            monologue_owner = "p1"
            self.log.append(f"💬 **{char1['nom']}** commence son monologue ennuyeux ! 'Dans mon temps, on n'avait pas ces machins électroniques...'")

        if char2 and "blablabla" in char2.get("statuts", []):
            monologue_active = True
            monologue_owner = "p2"
            self.log.append(f"💬 **{char2['nom']}** commence son monologue ennuyeux ! 'Vous savez, quand j'étais jeune, les cartes Pokémon n'existaient pas...'")
        
        if monologue_active:
            self.log.append(f"💬 Tout le monde est trop poli pour interrompre le monologue. Aucune attaque n'aura lieu ce tour !")
            embed = self._create_combat_embed("Monologue en cours...")
            combat_message = await self.channel.send(embed=embed)
            await asyncio.sleep(3)
            embed = self._create_combat_embed("Le monologue est terminé.")        
            await combat_message.edit(embed=embed)        
            await asyncio.sleep(3)        
            await self._end_combat_phase()      
            return
        # Vérifier si un des personnages sur le terrain a le statut "blablabl
        
        
        if char1 and "Parapluie" in char1.get("statuts", []):        
            self.p1_state['parapluie_active'] = True        
            self.log.append(f"☔ L'effet Parapluie de **{char1['nom']}** est activé pour ce combat !")           
        if char2 and "Parapluie" in char2.get("statuts", []):        
            self.p2_state['parapluie_active'] = True        
            self.log.append(f"☔ L'effet Parapluie de **{char2['nom']}** est activé pour ce combat !")

            
        # Vérifier et appliquer l'effet des spores (Dame champis)
        if char1 and "Champignon" in char1.get("statuts", []):
            # Appliquer le statut "Empoisonné" à tous les personnages de l'inventaire adverse
            for inv_char in self.p2_state['inventaire']:
                if inv_char:
                    if "statuts" not in inv_char:
                        inv_char["statuts"] = []
                    if "Empoisonné" not in inv_char["statuts"]:
                        inv_char["statuts"].append("Empoisonné")
    
            # Appliquer aussi au personnage sur le terrain s'il y en a un
            if char2:
                if "statuts" not in char2:
                    char2["statuts"] = []
                if "Empoisonné" not in char2["statuts"]:
                    char2["statuts"].append("Empoisonné")
    
            self.log.append(f"🍄 **{char1['nom']}** libère ses spores toxiques ! Tous les personnages adverses sont empoisonnés !")

        # Faire de même pour le joueur 2
        if char2 and "Champignon" in char2.get("statuts", []):
            # Appliquer le statut "Empoisonné" à tous les personnages de l'inventaire adverse
            for inv_char in self.p1_state['inventaire']:
                if inv_char:
                    if "statuts" not in inv_char:
                        inv_char["statuts"] = []
                    if "Empoisonné" not in inv_char["statuts"]:
                        inv_char["statuts"].append("Empoisonné")
    
            # Appliquer aussi au personnage sur le terrain s'il y en a un
            if char1:
                if "statuts" not in char1:
                    char1["statuts"] = []
                if "Empoisonné" not in char1["statuts"]:
                    char1["statuts"].append("Empoisonné")
    
            self.log.append(f"🍄 **{char2['nom']}** libère ses spores toxiques ! Tous les personnages adverses sont empoisonnés !")
            
        # Vérifier et appliquer le statut "Cadeau de Noël" (Sapin de Noël)
        if char1 and char2:  # Les deux personnages doivent être présents
            if "Cadeau de Noël" in char1.get("statuts", []):
                if "statuts" not in char2:
                    char2["statuts"] = []
                if "Malédiction" not in char2["statuts"]:
                    char2["statuts"].append("Malédiction")
                    self.log.append(f"🎄 **{char1['nom']}** donne une malédiction à **{char2['nom']}** !")
            
            if "Cadeau de Noël" in char2.get("statuts", []):
                if "statuts" not in char1:
                    char1["statuts"] = []
                if "Malédiction" not in char1["statuts"]:
                    char1["statuts"].append("Malédiction")
                    self.log.append(f"🎄 **{char2['nom']}** donne une malédiction à **{char1['nom']}** !")
                    
        # Vérifier et appliquer le statut "Typhon" (Tempête)
        if char1 and char2 and "Typhon" in char1.get("statuts", []):
            # Trouver un emplacement vide dans l'inventaire adverse
            empty_slot = None
            try:
                empty_slot = self.p2_state['inventaire'].index(None)
            except ValueError:
                self.log.append(f"🌪️ **{char1['nom']}** ne peut pas utiliser Bourrasque car l'inventaire adverse est plein !")
            
            if empty_slot is not None:
                # Trouver le personnage avec les PV les plus bas dans l'inventaire adverse
                replacement_char = None
                lowest_pv = float('inf')
                replacement_index = None
                
                for i, inv_char in enumerate(self.p2_state['inventaire']):
                    if inv_char and inv_char['pv'] < lowest_pv:
                        lowest_pv = inv_char['pv']
                        replacement_char = inv_char
                        replacement_index = i
                
                if replacement_char:
                    # Renvoyer le personnage du terrain dans l'inventaire
                    self.p2_state['inventaire'][empty_slot] = self.p2_state['terrain']
                    
                    # Placer le personnage de remplacement sur le terrain
                    self.p2_state['terrain'] = replacement_char
                    self.p2_state['inventaire'][replacement_index] = None
                    
                    self.log.append(f"🌪️ **{char1['nom']}** utilise Bourrasque ! **{self.p2_state['inventaire'][empty_slot]['nom']}** est renvoyé dans l'inventaire et remplacé par **{replacement_char['nom']}** !")
                    
                    # Mettre à jour char2 pour la suite du combat
                    char2 = self.p2_state['terrain']
                else:
                    self.log.append(f"🌪️ **{char1['nom']}** ne peut pas utiliser Bourrasque car il n'y a pas d'autre personnage dans l'inventaire adverse !")
            
            # Supprimer le statut après utilisation
            char1["statuts"].remove("Typhon")

        # Faire la même chose pour le joueur 2
        if char1 and char2 and "Typhon" in char2.get("statuts", []):
            # Trouver un emplacement vide dans l'inventaire adverse
            empty_slot = None
            try:
                empty_slot = self.p1_state['inventaire'].index(None)
            except ValueError:
                self.log.append(f"🌪️ **{char2['nom']}** ne peut pas utiliser Bourrasque car l'inventaire adverse est plein !")
            
            if empty_slot is not None:
                # Trouver le personnage avec les PV les plus bas dans l'inventaire adverse
                replacement_char = None
                lowest_pv = float('inf')
                replacement_index = None
                
                for i, inv_char in enumerate(self.p1_state['inventaire']):
                    if inv_char and inv_char['pv'] < lowest_pv:
                        lowest_pv = inv_char['pv']
                        replacement_char = inv_char
                        replacement_index = i
                
                if replacement_char:
                    # Renvoyer le personnage du terrain dans l'inventaire
                    self.p1_state['inventaire'][empty_slot] = self.p1_state['terrain']
                    
                    # Placer le personnage de remplacement sur le terrain
                    self.p1_state['terrain'] = replacement_char
                    self.p1_state['inventaire'][replacement_index] = None
                    
                    self.log.append(f"🌪️ **{char2['nom']}** utilise Bourrasque ! **{self.p1_state['inventaire'][empty_slot]['nom']}** est renvoyé dans l'inventaire et remplacé par **{replacement_char['nom']}** !")
                    
                    # Mettre à jour char1 pour la suite du combat
                    char1 = self.p1_state['terrain']
                else:
                    self.log.append(f"🌪️ **{char2['nom']}** ne peut pas utiliser Bourrasque car il n'y a pas d'autre personnage dans l'inventaire adverse !")
            
            # Supprimer le statut après utilisation
            char2["statuts"].remove("Typhon")

        if char1 and "Sommeil" in char1.get("statuts", []):            
            self.log.append(f"💤 **{char1['nom']}** est en Sommeil et ne peut pas être attaqué ce tour.")            
            char1['pv'] = char1['pv_max'] # Assure que les PV ne descendent pas en dessous de 0                
        if char2 and "Sommeil" in char2.get("statuts", []):            
            self.log.append(f"💤 **{char2['nom']}** est en Sommeil et ne peut pas être attaqué ce tour.")            
            char2['pv'] = char2['pv_max'] # Assure que les PV ne descendent pas en dessous de 0        
            # Cas particulier : aucun des deux joueurs n'a de personnage sur le terrain
        
        
        if char1 and "Incantation" in char1.get("statuts", []):            
            self.log.append(f"🔥 **{char1['nom']}** lance sa **Boule de feu** !")            
            if char2 and "Contre" in char2.get("statuts", []):            
                self.log.append(f"⚔️ **{char2['nom']}** contre la Boule de feu et la renvoie !")            
                self.p1_state['hp'] -= 15            
                self.log.append(f"❤️ **{self.p1_state['member'].display_name}** subit 15 points de dégâts de sa propre Boule de feu !")        
            else:            
                self.p2_state['hp'] -= 15            
                self.log.append(f"❤️ **{self.p2_state['member'].display_name}** subit 15 points de dégâts !")           
        if char2 and "Incantation" in char2.get("statuts", []):            
            self.log.append(f"🔥 **{char2['nom']}** lance sa **Boule de feu** !")            
            if char1 and "Contre" in char1.get("statuts", []):            
                self.log.append(f"⚔️ **{char1['nom']}** contre la Boule de feu et la renvoie !")            
                self.p2_state['hp'] -= 15            
                self.log.append(f"❤️ **{self.p2_state['member'].display_name}** subit 15 points de dégâts de sa propre Boule de feu !")        
            else:            
                self.p1_state['hp'] -= 15            
                self.log.append(f"❤️ **{self.p1_state['member'].display_name}** subit 15 points de dégâts !")          
        
        if char1 and char2: # Il faut que les deux personnages existent            
            # La Chasseuse du joueur 1 applique "Recherché" au joueur 2            
            if "En chasse" in char1.get("statuts", []):                
                if "statuts" not in char2: char2["statuts"] = []                
                if "Recherché" not in char2["statuts"]:                    
                    char2["statuts"].append("Recherché")                    
                    self.log.append(f"🎯 **{char1['nom']}** a marqué **{char2['nom']}** comme 'Recherché' !")            
                    # La Chasseuse du joueur 2 applique "Recherché" au joueur 1            
            
            if "En chasse" in char2.get("statuts", []):                
                if "statuts" not in char1: char1["statuts"] = []                
                if "Recherché" not in char1["statuts"]:                    
                    char1["statuts"].append("Recherché")                    
                    self.log.append(f"🎯 **{char2['nom']}** a marqué **{char1['nom']}** comme 'Recherché' !")

        # Vérifier et appliquer l'effet du statut "Malicieux" (Fouine)
        if char1 and char2:  # Les deux personnages doivent être présents
            if "Malicieux" in char1.get("statuts", []):
                # Échanger les personnages
                self.log.append(f"🦝 **{char1['nom']}** active son tour de passe-passe ! Elle échange sa place avec **{char2['nom']}** !")
                self.p1_state['terrain'], self.p2_state['terrain'] = self.p2_state['terrain'], self.p1_state['terrain']
                
                # Mettre à jour les variables locales après l'échange
                char1 = self.p1_state['terrain']
                char2 = self.p2_state['terrain']
            
            elif "Malicieux" in char2.get("statuts", []):
                # Échanger les personnages
                self.log.append(f"🦝 **{char2['nom']}** active son tour de passe-passe ! Elle échange sa place avec **{char1['nom']}** !")
                self.p1_state['terrain'], self.p2_state['terrain'] = self.p2_state['terrain'], self.p1_state['terrain']
                
                # Mettre à jour les variables locales après l'échange
                char1 = self.p1_state['terrain']
                char2 = self.p2_state['terrain']
        
        attack_order, reason = self._determine_attack_order()        
        # Logique du bonus d'attaque    
        winner_id = attack_order[0]    
        winner_state = self.game_state['players'][winner_id]        
        # Vérifier si le gagnant a le passif Vif    
        '''if 'vif' in winner_state.get('passives', {}):        
            # Vérifier s'il aurait gagné de toute façon (sans le passif)        
            base_order_winner_id = self._determine_base_attack_order()[0]        
            if winner_id == base_order_winner_id:            
                self.log.append(f"⚡ Le passif **Vif** de **{winner_state['member'].display_name}** se surpasse ! Il lance une attaque bonus !")                        
                # Exécuter l'attaque bonus            
                defender_id = self.p2_id if winner_id == self.p1_id else self.p1_id            
                defender_state = self.game_state['players'][defender_id]            
                self._execute_attack(winner_state, defender_state, i=-1) # i=-1 pour signifier "hors-combat"                        
                # Mettre à jour l'embed pour montrer le résultat du bonus            
                embed = self._create_combat_embed("Attaque bonus !")            
                combat_message = await self.channel.send(embed=embed)            
                await asyncio.sleep(4)''' # Pause pour que les joueurs voient l'attaque    # Affichage du message d'initiative (maintenant dynamique)    
        if reason == "passif":        
            self.log.append(f"⚡ **{winner_state['member'].display_name}** a l'initiative grâce à son passif **Vif** !")    
        else:        
            self.log.append(f"▶️ **{self.game_state['players'][attack_order[0]]['member'].display_name}** a l'initiative !")
        # Si le monologue est actif, on saute toutes les attaques
        embed = self._create_combat_embed("Le combat commence !")
        try:        
            await combat_message.edit(embed=embed)    
        except NameError:        
            combat_message = await self.channel.send(embed=embed)
        await asyncio.sleep(3)

            # Boucle pour les 3 attaques par personnage
        for i in range(3):
                # Tour de chaque joueur dans l'ordre d'initiative
                for attacker_id in attack_order:
                    # Si un joueur a perdu tous ses HP, on arrête immédiatement le combat
                    if self.p1_state['hp'] <= 0:            
                        # Vérifier si le joueur a le passif "Deuxième chance" actif            
                        if 'passives' in self.p1_state and 'second_chance' in self.p1_state['passives'] and self.p1_state['passives']['second_chance']:                
                            self.p1_state['hp'] = 20                
                            self.p1_state['passives']['second_chance'] = False  # Désactiver le passif après utilisation                
                            self.log.append(f"🔄 **{self.p1_state['member'].display_name}** active son passif Deuxième chance et regagne 20 HP!")            
                        else:                
                            break  # Fin du combat si pas de passif ou déjà utilisé                        
                    
                    if self.p2_state['hp'] <= 0:            
                        # Vérifier si le joueur a le passif "Deuxième chance" actif            
                        if 'passives' in self.p2_state and 'second_chance' in self.p2_state['passives'] and self.p2_state['passives']['second_chance']:                
                            self.p2_state['hp'] = 20                
                            self.p2_state['passives']['second_chance'] = False  # Désactiver le passif après utilisation                
                            self.log.append(f"🔄 **{self.p2_state['member'].display_name}** active son passif Deuxième chance et regagne 20 HP!")            
                        else:                
                            break

                    defender_id = self.p2_id if attacker_id == self.p1_id else self.p1_id
                    
                    attacker_state = self.game_state['players'][attacker_id]
                    defender_state = self.game_state['players'][defender_id]
                    
                    self._execute_attack(attacker_state, defender_state, i)

                    embed = self._create_combat_embed("Le combat continue...")
                    await combat_message.edit(embed=embed)
                    await asyncio.sleep(4) # Un peu plus de temps pour lire
                    
        for attacker_id in attack_order:            
                attacker_state = self.game_state['players'][attacker_id]            
                if attacker_state['terrain'] and "Art abstrait" in attacker_state['terrain'].get("statuts", []) and attacker_state['terrain']['pv'] > 0:                
                    defender_id = self.p2_id if attacker_id == self.p1_id else self.p1_id                
                    defender_state = self.game_state['players'][defender_id]                
                    self.log.append(f"🎨 **{attacker_state['terrain']['nom']}** lance une attaque bonus !")                
                    self._execute_attack(attacker_state, defender_state, 3)                
                    embed = self._create_combat_embed("Attaque supplémentaire !")                
                    await combat_message.edit(embed=embed)                
                    await asyncio.sleep(4)

        self.log.append("Fin du round de combat.")
        embed = self._create_combat_embed("Le round est terminé.")
        await combat_message.edit(embed=embed)
        await asyncio.sleep(3)
        await self._end_combat_phase()
        


    # Dans cogs/combat_engine_1v1.py, classe CombatEngine

    async def _end_combat_phase(self):
        """Termine la phase de combat, distribue les récompenses et prépare la phase suivante."""
        self.log.clear()

        for p_id, p_state in self.game_state['players'].items():
            # --- LOGIQUE QUI NE TOUCHE PAS AUX MPs ---
            pr_gain = 6 if 'mode_facile' in p_state.get('passives', {}) else 4
            p_state['pr'] += pr_gain

            for inv_char in p_state['inventaire']:
                if inv_char and "statuts" in inv_char and "Fatigue d'invocation" in inv_char["statuts"]:
                    inv_char["statuts"].remove("Fatigue d'invocation")

            if p_state['terrain']:
                if "Sommeil" in p_state['terrain'].get("statuts", []):
                    self.log.append(f"💤 **{p_state['terrain']['nom']}** disparaît après son petit effort.")
                    p_state['terrain'] = None
                
                if p_state['terrain'] and "Cape Guerrière" in p_state['terrain'].get("statuts", []):
                    cape_char = {"nom": "Cape guerrière", "pv": 4, "pv_max": 4, "attaque": 4, "capacite": {"nom": "Revêtement", "cout": 5}}
                    p_state['terrain']["statuts"].remove("Cape Guerrière")
                    p_state['terrain']['pv'] -= cape_char['pv']
                    p_state['terrain']['attaque'] -= cape_char['attaque']
                    try:
                        empty_slot = p_state['inventaire'].index(None)
                        p_state['inventaire'][empty_slot] = cape_char
                        self.log.append(f"🧥 **{cape_char['nom']}** retourne à l'inventaire.")
                    except ValueError:
                        self.log.append(f"🧥 **{cape_char['nom']}** ne peut pas revenir à l'inventaire et est détruite.")

                if p_state['terrain'] and p_state['terrain'].get("statuts"):
                    for status in p_state['terrain']["statuts"][:]:
                        if status in ["Flotte", "En chasse", "À l'affût", "Incantation", "Sommeil", "Coton", "Art abstrait", "Art contemporain", "Parapluie", "Contre", "Cadeau de Noël", "Calin", "Typhon", "Champignon", "blablabla", "Vol", "Malicieux", "Volonté"]:
                            p_state['terrain']["statuts"].remove(status)
            
            p_state['parapluie_active'] = False

            # --- GESTION DES NOTIFICATIONS MP (AVEC LA RÈGLE D'OR) ---
            if not p_state.get('is_ai'):
                try:
                    member = p_state['member']
                    dm_channel = member.dm_channel or await member.create_dm()

                    # Notification de gain de PR
                    await dm_channel.send(f"✅ Vous avez gagné **{pr_gain} PR** pour le prochain tour.")

                    # Notification pour "Absentéisme"
                    if 'absenteism' in p_state.get('passives', {}) and not p_state.get('has_placed_character', False):
                        p_state['pr'] += 4
                        await dm_channel.send(f"💸 Votre passif **Absentéisme** s'active ! Vous recevez +4 PR.")
                        await self.channel.send(f"💸 Le passif **Absentéisme** de **{p_state['member'].display_name}** s'active !")

                    # Notification pour "Tactique de la marée humaine"
                    if 'human_tide' in p_state.get('passives', {}) and all(c is not None for c in p_state['inventaire']):
                        for inv_char in p_state['inventaire']:
                            if "Envoûté" not in inv_char.get("statuts", []):
                                inv_char['attaque'] += 3
                        await dm_channel.send(f"👥 Votre passif **Tactique de la marée humaine** s'active ! Vos personnages en inventaire gagnent +3 ATQ.(sauf les Envoûtés)")
                        await self.channel.send(f"👥 Le passif **Tactique de la marée humaine** de **{p_state['member'].display_name}** s'active !")

                except discord.Forbidden:
                    pass # Le joueur a bloqué les MPs, on continue silencieusement
            else: # Si c'est une IA, on applique la logique sans envoyer de MP
                if 'absenteism' in p_state.get('passives', {}) and not p_state.get('has_placed_character', False):
                    p_state['pr'] += 4
                    await self.channel.send(f"💸 Le passif **Absentéisme** de **{p_state['member'].display_name}** s'active !")
                inventory_full = all(c is not None for c in p_state['inventaire'])
                if 'human_tide' in p_state.get('passives', {}) and inventory_full:
                    for inv_char in p_state['inventaire']:
                        if "Envoûté" not in inv_char.get("statuts", []):
                            inv_char['attaque'] += 3
                    await self.channel.send(f"👥 Le passif **Tactique de la marée humaine** de **{p_state['member'].display_name}** s'active !")

        await self._send_post_combat_report(self.p1_state, self.p2_state)
        await self._send_post_combat_report(self.p2_state, self.p1_state)
        await asyncio.sleep(1)

        self.game_state['phase'] = 'preparation'
        self.game_state['tour'] += 1