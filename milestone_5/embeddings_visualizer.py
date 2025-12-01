import json
import numpy as np
import pandas as pd
import plotly.express as px
from sklearn.manifold import TSNE

from db_manager import DBManager


def fetch_data_sql():
    """
    Scarica i dati usando una connessione Raw SQL diretta.
    Bypassa i limiti dell'API HTTP di Supabase.
    """
    try:
        conn = DBManager.get_raw_connection()
        cursor = conn.cursor()

        query = """
                SELECT title, main_category, category, brand, price, img_embedding
                FROM product_data
                WHERE img_embedding IS NOT NULL \
                """

        cursor.execute(query)

        rows = cursor.fetchall()
        colnames = [desc[0] for desc in cursor.description]

        cursor.close()
        conn.close()

        if not rows:
            return None

        return pd.DataFrame(rows, columns=colnames)

    except Exception as e:
        return None

def process_embeddings(df):
    """
    Converte la colonna img_embedding in matrice numpy.
    Nota: Con psycopg2 (il driver standard), i vettori pgvector arrivano spesso
    come stringhe '[0.1, 0.2...]' se non c'è un adapter specifico registrato,
    oppure come liste. Questo codice gestisce entrambi i casi.
    """
    print("⚙️ Elaborazione vettori...")

    def parse_embedding(val):
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return json.loads(val)
        return val

    # Applica il parsing
    embeddings_list = df['img_embedding'].apply(parse_embedding).tolist()
    matrix = np.array(embeddings_list)

    print(f"📊 Matrice pronta: {matrix.shape}")
    return matrix

def visualize_tsne(df, matrix):
    """
    Applica t-SNE e genera il grafico Plotly.
    """

    tsne = TSNE(n_components=2, perplexity=40, random_state=42, init='pca', learning_rate='auto')
    projections = tsne.fit_transform(matrix)

    df['x'] = projections[:, 0]
    df['y'] = projections[:, 1]

    df['main_category'] = df['main_category'].fillna('N/A')
    df['brand'] = df['brand'].fillna('N/A')

    fig = px.scatter(
        df,
        x='x',
        y='y',
        color='main_category', # Puoi cambiarlo con 'brand' o 'category'
        hover_data=['title', 'price', 'brand', 'category'],
        title=f'Images Latent Space using t-SNE ({len(df)} items)',
        height=900,
        template='plotly_white'
    )

    fig.update_xaxes(showticklabels=False, visible=False)
    fig.update_yaxes(showticklabels=False, visible=False)

    # Aggiunge un selettore per filtrare cliccando sulla legenda
    fig.update_layout(legend_title_text='Category')

    fig.show()

def visualize_embeddings():
    df = fetch_data_sql()
    if df is not None and not df.empty:
        matrix = process_embeddings(df)
        visualize_tsne(df, matrix)
    else:
        print("Nessun dato da visualizzare.")