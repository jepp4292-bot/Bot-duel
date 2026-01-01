# cogs/ai_strategist.py
import random
import copy
import logging

class AIStrategist:
    """
    Une IA avancée conçue pour analyser, planifier et s'adapter.
    Elle fonctionne sur un modèle en 3 phases : Analyse, Planification, Exécution.
    """
    def __init__(self, bot):
        self.bot = bot
        self.current_plan = "STANDARD" # Le plan de jeu actuel de l'IA

    # =====================================================================================
    # PHASE 1 : ANALYSE (LE CERVEAU DE RENSEIGNEMENT)
    # =====================================================================================

    def _identify_archetype(self, player_state):
        """Tente d'identifier le style de jeu d'un joueur en se basant sur ses passifs et personnages."""
        # Compteurs pour chaque archétype
        scores = {"AGGRO": 0, "CONTROL": 0, "COMBO": 0, "ECONOMY": 0}

        # Analyse des passifs
        passives = player_state.get('passives', {})
        if 'vif' in passives or 'a_main_nue' in passives:
            scores["AGGRO"] += 2
        if 'volonte' in passives or 'second_chance' in passives:
            scores["CONTROL"] += 2
        if 'mode_facile' in passives or 'pret' in passives or 'absenteism' in passives:
            scores["ECONOMY"] += 3
        if 'promotion' in passives or 'maitre_capacites' in passives:
            scores["COMBO"] += 2

        # Analyse des personnages (inventaire + terrain)
        all_chars = [c for c in player_state['inventaire'] if c] + ([player_state['terrain']] if player_state['terrain'] else [])
        for char in all_chars:
            roles = char.get('roles', [])
            if 'dps' in roles or 'nuker' in roles:
                scores["AGGRO"] += 1
                scores["COMBO"] += 1
            if 'tank' in roles or 'support' in roles:
                scores["CONTROL"] += 1
            if 'economy' in roles:
                scores["ECONOMY"] += 1

        # Retourne l'archétype avec le score le plus élevé
        if not all_chars and not passives: return "INCONNU"
        return max(scores, key=scores.get)

    def _analyze_game_state(self, player_state, opponent_state, game_state):
        """Crée un dictionnaire de contexte complet sur l'état du jeu."""
        context = {}
        
        # Analyse de la menace et du danger
        player_hp = player_state['hp']
        danger_score = 0
        if player_hp < 15: danger_score += 50
        elif player_hp < 25: danger_score += 25

        opponent_char = opponent_state.get('terrain')
        if opponent_char:
            # Menace imminente du personnage sur le terrain
            if opponent_char['attaque'] >= 7: danger_score += 25
            if "Contre" in opponent_char.get("statuts", []): danger_score += 15 # Menace indirecte

        context['danger_level'] = danger_score

        # Analyse des archétypes
        context['my_archetype'] = self._identify_archetype(player_state)
        context['opponent_archetype'] = self._identify_archetype(opponent_state)

        # Analyse des ressources
        context['pr_advantage'] = player_state['pr'] - opponent_state['pr']

        return context

    # =====================================================================================
    # PHASE 2 : PLANIFICATION (LE CERVEAU STRATÉGIQUE)
    # =====================================================================================

    def _determine_game_plan(self, context, player_state, opponent_state):
        """Définit le plan de jeu pour le tour actuel."""
        
        # Règle prioritaire : la survie avant tout
        if context['danger_level'] >= 60:
            self.current_plan = "SURVIE_IMMEDIATE"
            return

        # Adaptation à l'archétype adverse
        opponent_archetype = context['opponent_archetype']
        if opponent_archetype == "AGGRO":
            # Si on est en avance en PV, on peut se permettre de se battre. Sinon, on défend.
            self.current_plan = "DEFENSE_CONTRE_AGGRO" if player_state['hp'] < opponent_state['hp'] else "TRADE_EFFICIENTLY"
        elif opponent_archetype == "CONTROL":
            # Contre un joueur contrôle, la clé est l'économie.
            self.current_plan = "GUERRE_ECONOMIQUE"
        elif opponent_archetype == "COMBO":
            # Contre un combo, il faut le tuer avant qu'il ne soit prêt.
            self.current_plan = "PRESSION_AGRESSIVE"
        else: # INCONNU ou ECONOMY
            self.current_plan = "DEVELOPPEMENT"

        logging.info(f"[IA STRATÈGE - PLAN] Nouveau plan : {self.current_plan} (Danger: {context['danger_level']})")

    # =====================================================================================
    # PHASE 3 : EXÉCUTION (LE CERVEAU TACTIQUE)
    # =====================================================================================

    def _score_character_for_plan(self, char, plan, context):
        """Donne un score à un personnage en fonction du plan de jeu actuel."""
        score = char.get('pv_max', char['pv']) * 2 + char['attaque'] * 2.5
        roles = char.get('roles', [])

        if plan == "SURVIE_IMMEDIATE" or plan == "DEFENSE_CONTRE_AGGRO":
            if 'tank' in roles: score += 50
            if 'support' in roles: score += 30
        
        if plan == "PRESSION_AGRESSIVE" or plan == "TRADE_EFFICIENTLY":
            if 'dps' in roles: score += 40
            if 'nuker' in roles: score += 60

        if plan == "GUERRE_ECONOMIQUE":
            if 'economy' in roles: score += 50
        
        if "Fatigue d'invocation" in char.get("statuts", []):
            score -= 200 # Pénalité très lourde

        return score

    def _score_ability_for_plan(self, capacite, char, plan, context, player_state, opponent_state):
        """Donne un score de priorité à une capacité en fonction du plan."""
        priority = 0
        tags = capacite.get('tags', [])

        # Bonus/Malus basés sur le plan
        if plan == "SURVIE_IMMEDIATE" or plan == "DEFENSE_CONTRE_AGGRO":
            if 'defense' in tags or 'heal' in tags: priority += 60
        elif plan == "PRESSION_AGRESSIVE":
            if 'offensif' in tags or 'direct_damage' in tags: priority += 50
        elif plan == "GUERRE_ECONOMIQUE":
            if 'economy' in tags and 'debuff' in tags: priority += 70
        
        # Logique contextuelle (plus fine que l'IA de base)
        if 'direct_damage' in tags and opponent_state['hp'] < 15:
            priority = 200 # Priorité absolue pour achever l'adversaire
        
        # Anti-spam (comme on l'a vu précédemment)
        if capacite['nom'] == "Garde du corps" and "Garde du corps" in char.get("statuts", []):
            priority -= 40
            
        return priority

    def _consider_loan(self, player_state, opponent_state, game_state):
        """Logique complexe pour décider d'utiliser le passif 'Prêt'."""
        if not ('pret' in player_state.get('passives', {}) and not player_state.get('a_emprunte_ce_tour', False)):
            return # Ne peut pas emprunter

        # Scénario 1 : Emprunter pour une action de victoire
        # On simule un emprunt pour voir si on peut invoquer et utiliser une capacité de Nuke
        for char in player_state['inventaire']:
            if char and 'nuker' in char.get('roles', []):
                total_cost = char['capacite']['cout']
                pr_needed = total_cost - player_state['pr']
                if 0 < pr_needed <= 10 and char['capacite']['nom'] == "Boule de feu": # 15 dégâts
                    if opponent_state['hp'] <= 15:
                        logging.info("[IA STRATÈGE - PRÊT] Emprunt pour la victoire !")
                        return pr_needed

        # Scénario 2 : Emprunter pour survivre
        # Si on est très bas en PV et qu'un soin peut nous sauver
        if player_state['hp'] < 10:
            for char in player_state['inventaire']:
                if char and 'heal' in char.get('capacite', {}).get('tags', []):
                    pr_needed = char['capacite']['cout'] - player_state['pr']
                    if 0 < pr_needed <= 10:
                        logging.info("[IA STRATÈGE - PRÊT] Emprunt pour survivre !")
                        return pr_needed
        
        # Scénario 3 : Emprunt de tempo en début de partie
        if game_state['tour'] <= 3 and player_state['pr'] >= 4:
             # Emprunter pour invoquer un personnage à coût moyen (4-6)
             if any(4 <= char['cout'] <= 6 for char in self.bot.catalogue_personnages_1v1.values()):
                 loan_amount = random.randint(2, 4)
                 logging.info(f"[IA STRATÈGE - PRÊT] Emprunt de tempo de {loan_amount} PR.")
                 return loan_amount

        return None # Pas de raison d'emprunter
    
    # Dans cogs/ai_strategist.py, à l'intérieur de la classe AIStrategist

    def choisir_passif(self, player_state, available_passives_ids, game_state):
        """
        Choisit un passif en se basant sur une analyse stratégique approfondie de tous les passifs disponibles.
        """
        # Pour faire un choix éclairé, l'IA a besoin d'une analyse complète de la situation.
        opponent_state = next((p for p_id, p in game_state['players'].items() if p_id != player_state['member'].id), None)
        if not opponent_state: return # Sécurité si l'adversaire n'est pas trouvé

        context = self._analyze_game_state(player_state, opponent_state, game_state)
        opponent_archetype = context['opponent_archetype']

        best_passive = None
        best_score = -1

        logging.info(f"[IA STRATÈGE - PASSIF] Analyse des choix pour contrer l'archétype : {opponent_archetype}")

        for passive_id in available_passives_ids:
            score = 0
            
            # --- ÉVALUATION INDIVIDUELLE DE CHAQUE PASSIF ---

            if passive_id in ["second_chance", "volonte"]:
                # PASSIFS DE SURVIE : Priorité absolue en cas de danger.
                # 'volonte' est légèrement meilleur en milieu de partie, 'second_chance' est un joker final.
                score = 95 if context['danger_level'] >= 50 else 65
                if player_state['hp'] <= 20: score = 110 # Urgence maximale

            elif passive_id == "absenteism":
                # PASSIF ÉCONOMIQUE CONDITIONNEL : Très fort si on peut se le permettre.
                # Intéressant si notre personnage sur le terrain est un tank solide qui va probablement survivre.
                terrain_char = player_state.get('terrain')
                if terrain_char and terrain_char.get('pv_max', 0) >= 10:
                    score = 80
                else:
                    score = 40 # Trop risqué si on n'a personne ou un personnage fragile.

            elif passive_id == "human_tide":
                # PASSIF D'AGRESSION DE MASSE : Nécessite d'avoir déjà un inventaire rempli.
                inventory_count = sum(1 for c in player_state['inventaire'] if c)
                if inventory_count >= 2:
                    score = 90 # Excellent pour mettre une pression énorme.
                else:
                    score = 50 # Un pari sur le futur, moins prioritaire.

            elif passive_id == "maitre_capacites":
                # PASSIF DE COMBO : Idéal si on a des capacités coûteuses en main.
                has_expensive_ability = any(c and c.get('capacite', {}).get('cout', 0) >= 4 for c in player_state['inventaire'])
                score = 85 if has_expensive_ability else 60

            elif passive_id == "pret":
                # PASSIF À HAUT RISQUE : Le plus complexe. On ne le prend que si un emprunt peut changer la partie.
                # Scénario 1: On peut achever l'adversaire ce tour-ci.
                if opponent_state['hp'] <= 15:
                    score = 90
                # Scénario 2: On peut se sauver d'une situation désespérée.
                elif player_state['hp'] <= 15 and any(c and 'heal' in c.get('capacite', {}).get('tags', []) for c in player_state['inventaire']):
                    score = 90
                # Scénario 3: C'est le début de partie, un petit emprunt peut accélérer notre jeu.
                elif game_state['tour'] == 2:
                    score = 75
                else:
                    score = 55 # Moins intéressant en fin de partie si pas décisif.

            elif passive_id == "mode_facile":
                # PASSIF ÉCONOMIQUE FIABLE : Presque jamais un mauvais choix.
                # Particulièrement fort contre les stratégies de contrôle où la partie dure longtemps.
                score = 85
                if opponent_archetype == "CONTROL":
                    score = 95

            elif passive_id == "promotion":
                # PASSIF DE COMBO SPÉCIFIQUE : Divin si on a les bons personnages.
                has_promo_target = any(c and c.get('cout', 0) in [6, 7, 8] for c in player_state['inventaire'])
                score = 100 if has_promo_target else 45

            elif passive_id == "a_main_nue":
                # PASSIF DE COMBAT SOLIDE : Rend nos personnages plus résistants pour les premiers échanges.
                # Très bon contre les stratégies agressives où les PV supplémentaires font la différence.
                score = 75
                if opponent_archetype == "AGGRO":
                    score = 85

            elif passive_id == "vif":
                # PASSIF DE TEMPO : L'un des meilleurs. Permet de dicter le rythme du combat.
                # Absolument crucial pour tuer un attaquant adverse avant qu'il n'agisse.
                score = 80
                if opponent_archetype in ["AGGRO", "COMBO"]:
                    score = 100 # Contre direct à ces stratégies.

            else:
                score = 50 # Score de base pour tout passif non listé.

            logging.info(f"    -> Évaluation de '{passive_id}': Score = {score}")
            if score > best_score:
                best_score = score
                best_passive = passive_id
        
        if best_passive:
            player_state['passives'][best_passive] = True
            logging.info(f"[IA STRATÈGE - PASSIF] Choix final : **{best_passive}** (Score: {best_score})")
        else:
            # Sécurité au cas où aucun passif ne serait disponible ou scorable
            fallback_passive = random.choice(list(available_passives_ids))
            player_state['passives'][fallback_passive] = True
            logging.info(f"[IA STRATÈGE - PASSIF] AVERTISSEMENT : Aucun score positif, choix aléatoire : **{fallback_passive}**")


    # Dans cogs/ai_strategist.py
# REMPLACEZ l'ancienne méthode make_decisions par celle-ci :

    # Dans cogs/ai_strategist.py
# REMPLACEZ la méthode plan_turn existante par celle-ci :

    def plan_turn(self, player_state, opponent_state, game_state,invocation_choices: list ):
        """
        Analyse la situation et retourne un plan d'action complet pour le tour,
        basé sur une simulation rigoureuse qui respecte les règles du jeu.
        """
        # === PHASE 1: ANALYSE (une seule fois) ===
        context = self._analyze_game_state(player_state, opponent_state, game_state)
        self._determine_game_plan(context, player_state, opponent_state)
        
        # === PHASE 2: PLANIFICATION SIMULÉE ===
        simulated_state = copy.deepcopy(player_state)
        actions_plan = []
        max_actions = 3

        # === CORRECTION : On ajoute un drapeau pour la simulation de placement ===
        simulated_has_placed = False
        if simulated_state.get('terrain'):
            simulated_has_placed = True

        # Logique d'emprunt prioritaire
        loan_amount = self._consider_loan(simulated_state, opponent_state, game_state)
        if loan_amount:
            actions_plan.append({"action": "loan", "amount": loan_amount})
            simulated_state['pr'] += loan_amount
            simulated_state['dette'] -= loan_amount
            simulated_state['a_emprunte_ce_tour'] = True
            
        while len(actions_plan) < max_actions:
            best_action = None
            best_score = 15 # On augmente légèrement le seuil pour éviter les actions triviales

            # 1. Évaluer l'utilisation d'une capacité
            all_chars_slots = [(i, char) for i, char in enumerate(simulated_state['inventaire']) if char]
            if simulated_state['terrain']: all_chars_slots.append(("terrain", simulated_state['terrain']))

            for slot, char in all_chars_slots:
                if "capacite" in char and simulated_state['pr'] >= char['capacite']['cout']:
                    score = self._score_ability_for_plan(char['capacite'], char, self.current_plan, context, simulated_state, opponent_state)
                    if score > best_score:
                        best_score = score
                        best_action = {"action": "use_ability", "data": (slot, char, char['capacite'])}
            
            # 2. Évaluer le placement d'un personnage
            # === CORRECTION : On vérifie si un placement a déjà été simulé ===
            if not simulated_has_placed:
                placeable = [char for char in simulated_state['inventaire'] if char and "Fatigue d'invocation" not in char.get("statuts", [])]
                if placeable:
                    best_char_to_place = max(placeable, key=lambda c: self._score_character_for_plan(c, self.current_plan, context))
                    placement_score = self._score_character_for_plan(best_char_to_place, self.current_plan, context)
                    
                    if placement_score > best_score:
                        if not simulated_state['terrain'] or placement_score > self._score_character_for_plan(simulated_state['terrain'], self.current_plan, context) + 20:
                            best_score = placement_score
                            idx = simulated_state['inventaire'].index(best_char_to_place)
                            best_action = {"action": "place_character", "slot": idx}

            # 3. Évaluer l'invocation d'un personnage
            if None in simulated_state['inventaire'] and simulated_state['pr'] > 0:
                choices = invocation_choices
                if choices:
                    affordable_choices = [c for c in choices if c['cout'] <= simulated_state['pr']]
                    if affordable_choices:
                        best_char_to_invoke = max(affordable_choices, key=lambda c: self._score_character_for_plan(c, self.current_plan, context))
                        invoke_score = self._score_character_for_plan(best_char_to_invoke, self.current_plan, context)
                    
                        if invoke_score > best_score:
                            best_score = invoke_score
                            slot = simulated_state['inventaire'].index(None)
                            best_action = {"action": "invoke", "char_name": best_char_to_invoke['nom'], "slot": slot}

            # Si une action a été choisie, on l'ajoute au plan et on met à jour l'état simulé
            if best_action:
                actions_plan.append(best_action)
                
                # Mise à jour de la simulation pour la prochaine itération
                if best_action['action'] == 'use_ability':
                    simulated_state['pr'] -= best_action['data'][2]['cout']
                
                elif best_action['action'] == 'place_character':
                    char_to_place = simulated_state['inventaire'][best_action['slot']]
                    if simulated_state['terrain']:
                        simulated_state['inventaire'][best_action['slot']] = simulated_state['terrain']
                    else:
                        simulated_state['inventaire'][best_action['slot']] = None
                    simulated_state['terrain'] = char_to_place
                    # === CORRECTION : On met à jour le drapeau de placement ===
                    simulated_has_placed = True
                
                elif best_action['action'] == 'invoke':
                    # === CORRECTION : Simulation d'invocation complète et fidèle ===
                    char_info = self.bot.catalogue_personnages_1v1[best_action['char_name']]
                    char_data = copy.deepcopy(char_info) # Très important pour ne pas modifier le catalogue
                    
                    simulated_state['pr'] -= char_data['cout']
                    
                    if 'pv_max' not in char_data:
                        char_data['pv_max'] = char_data['pv']
                    
                    if game_state['tour'] > 1:
                        if "statuts" not in char_data:
                            char_data["statuts"] = []
                        char_data["statuts"].append("Fatigue d'invocation")
                    
                    simulated_state['inventaire'][best_action['slot']] = char_data
            else:
                break
        
        if not actions_plan:
            return [{"action": "ready"}]

        return actions_plan
async def setup(bot):
     pass