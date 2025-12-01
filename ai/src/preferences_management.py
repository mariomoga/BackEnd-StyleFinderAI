from supabase import Client

def get_user_preferences(client: Client, user_id_key: int) -> tuple[dict, str | None] | tuple[None, None]:
    """
    Recupera le preferenze dell'utente dalla tabella relazionale 'user_preference'
    e le mappa nel formato piatto (favorite_color, favorite_material, ecc.)
    per mantenere la compatibilità.
    """

    try:
        # 1. Esegui la query usando la sintassi di Supabase per le JOIN.
        # Selezioniamo il 'value' dalla tabella di collegamento e il 'name' dalla tabella 'preferences'.
        # Corrisponde a: SELECT up.value, p.name FROM user_preference up INNER JOIN preferences p ...
        response = client.table('user_preference').select(
            'value, preferences(name)'
        ).eq('user_id', user_id_key).execute()

        # 2. Controlla se sono stati trovati dati
        if not response.data:
            # print(f"No preferences found for user ID: {user_id_key}")
            return None, None

        # 3. Trasforma la lista di righe in un unico dizionario
        # response.data sarà tipo: [{'value': 'black', 'preferences': {'name': 'color'}}, ...]
        result_prefs = {}
        gender = None

        for row in response.data:
            # Estrai il nome della preferenza (es. 'color', 'brand', 'gender')
            # Nota: 'preferences' qui è un oggetto annidato a causa della join
            pref_data = row.get('preferences')
            if not pref_data:
                continue

            p_name = pref_data.get('name')
            p_value = row.get('value')

            if p_name == 'gender':
                # Il genere viene estratto separatamente come nella funzione originale
                gender = p_value
            else:
                # Mappa i nomi standard del DB (es. 'color') nei nomi attesi dal tuo codice (es. 'favorite_color')
                key_name = f"favorite_{p_name}"
                result_prefs[key_name] = p_value

        return result_prefs, gender

    except Exception as e:
        print(f"Error retrieving user preferences for {user_id_key}: {e}")
        return None, None