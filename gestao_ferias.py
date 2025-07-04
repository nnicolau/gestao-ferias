import streamlit as st
import pandas as pd
from datetime import datetime
import sqlite3
from sqlite3 import Error
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Configuração inicial
st.set_page_config(page_title="Gestão de Férias", layout="wide")
st.image("Logotipo.png", width=100)
st.title("🗓️ Sistema de Gestão de Férias - INDICA7")

# Função para criar/conectar ao banco de dados
def criar_conexao():
    try:
        return sqlite3.connect('ferias.db')
    except Error as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")
        return None

# Criar tabelas se não existirem
def criar_tabelas(conn):
    try:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS funcionarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            data_admissao TEXT NOT NULL,
            dias_ferias INTEGER NOT NULL)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS ferias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            funcionario_id INTEGER NOT NULL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT NOT NULL,
            dias INTEGER NOT NULL,
            FOREIGN KEY (funcionario_id) REFERENCES funcionarios (id))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY,
            max_ferias_simultaneas INTEGER NOT NULL)''')

        cursor.execute('SELECT 1 FROM configuracoes WHERE id = 1')
        if not cursor.fetchone():
            cursor.execute('INSERT INTO configuracoes (id, max_ferias_simultaneas) VALUES (1, 2)')

        conn.commit()
    except Error as e:
        st.error(f"Erro ao criar tabelas: {e}")

# Funções auxiliares
def calcular_dias_uteis(inicio, fim):
    return len(pd.bdate_range(start=inicio, end=fim))

def verificar_limite_ferias(conn, nova_inicio, nova_fim, funcionario_id):
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT max_ferias_simultaneas FROM configuracoes WHERE id = 1')
        max_simultaneas = cursor.fetchone()[0]

        nova_inicio = pd.to_datetime(nova_inicio).date()
        nova_fim = pd.to_datetime(nova_fim).date()

        cursor.execute('''SELECT f.data_inicio, f.data_fim FROM ferias f
            WHERE f.funcionario_id != ?
            AND ((f.data_inicio BETWEEN ? AND ?) OR
                 (f.data_fim BETWEEN ? AND ?) OR
                 (? BETWEEN f.data_inicio AND f.data_fim) OR
                 (? BETWEEN f.data_inicio AND f.data_fim))''',
            (funcionario_id, nova_inicio, nova_fim, nova_inicio, nova_fim, nova_inicio, nova_fim))

        ferias_conflitantes = cursor.fetchall()
        calendario = pd.DataFrame(columns=['Data', 'Pessoas'])

        for inicio, fim in ferias_conflitantes:
            dias = pd.bdate_range(start=max(pd.to_datetime(inicio).date(), nova_inicio),
                                  end=min(pd.to_datetime(fim).date(), nova_fim))
            for dia in dias:
                calendario.loc[len(calendario)] = [dia, 1]

        if not calendario.empty:
            contagem = calendario.groupby('Data').sum()
            dias_problema = contagem[contagem['Pessoas'] >= max_simultaneas]
            if not dias_problema.empty:
                return False, dias_problema.index[0].strftime('%d/%m/%Y')

        return True, None
    except Error as e:
        st.error(f"Erro ao verificar limite de férias: {e}")
        return False, None

# Inicializar banco de dados
conn = criar_conexao()
if conn:
    criar_tabelas(conn)

# Sidebar
with st.sidebar:
    st.header("Configurações")
    if conn:
        cursor = conn.cursor()
        cursor.execute('SELECT max_ferias_simultaneas FROM configuracoes WHERE id = 1')
        max_atual = cursor.fetchone()[0]
        novo_max = st.number_input("Máximo em férias simultâneas", min_value=1, value=max_atual)
        if novo_max != max_atual:
            cursor.execute('UPDATE configuracoes SET max_ferias_simultaneas = ? WHERE id = 1', (novo_max,))
            conn.commit()
            st.success("Configuração atualizada!")

# Abas principais
tab1, tab2, tab3 = st.tabs(["Funcionários", "Férias", "Relatórios"])

with tab1:
    st.subheader("Gestão de Funcionários")
    with st.form("form_funcionario", clear_on_submit=True):
        nome = st.text_input("Nome")
        data_admissao = st.date_input("Data de admissão")
        dias_ferias = st.number_input("Dias de férias/ano", min_value=1, value=22)
        if st.form_submit_button("Adicionar"):
            try:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO funcionarios (nome, data_admissao, dias_ferias) VALUES (?, ?, ?)',
                               (nome, data_admissao.isoformat(), dias_ferias))
                conn.commit()
                st.success("Funcionário adicionado.")
            except Error as e:
                st.error(f"Erro: {e}")

    funcionarios = pd.read_sql('SELECT * FROM funcionarios', conn)
    if not funcionarios.empty:
        st.dataframe(funcionarios)
        with st.expander("Editar / Apagar Funcionários"):
            for _, row in funcionarios.iterrows():
                with st.form(f"editar_func_{row['id']}"):
                    novo_nome = st.text_input("Nome", value=row['nome'])
                    nova_data = st.date_input("Data de admissão", value=pd.to_datetime(row['data_admissao']))
                    novos_dias = st.number_input("Dias de férias", min_value=1, value=row['dias_ferias'])
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("Atualizar"):
                            cursor.execute('UPDATE funcionarios SET nome = ?, data_admissao = ?, dias_ferias = ? WHERE id = ?',
                                           (novo_nome, nova_data.isoformat(), novos_dias, row['id']))
                            conn.commit()
                            st.success("Atualizado.")
                            st.rerun()
                    with col2:
                        if st.form_submit_button("Apagar"):
                            cursor.execute('DELETE FROM funcionarios WHERE id = ?', (row['id'],))
                            conn.commit()
                            st.warning("Funcionário removido.")
                            st.rerun()

with tab2:
    st.subheader("Gestão de Férias")
    funcionarios = pd.read_sql('SELECT id, nome FROM funcionarios', conn)
    if not funcionarios.empty:
        with st.form("marcar_ferias", clear_on_submit=True):
            funcionario_id = st.selectbox("Funcionário", funcionarios['id'],
                format_func=lambda x: funcionarios.loc[funcionarios['id'] == x, 'nome'].values[0])
            col1, col2 = st.columns(2)
            with col1:
                data_inicio = st.date_input("Início")
            with col2:
                data_fim = st.date_input("Fim")
            if st.form_submit_button("Marcar"):
                if data_fim <= data_inicio:
                    st.error("Data final deve ser posterior à inicial.")
                else:
                    dias = calcular_dias_uteis(data_inicio, data_fim)
                    ok, dia_conflito = verificar_limite_ferias(conn, data_inicio, data_fim, funcionario_id)
                    if not ok:
                        st.error(f"Excesso de pessoas em férias no dia {dia_conflito}.")
                    else:
                        cursor = conn.cursor()
                        cursor.execute('INSERT INTO ferias (funcionario_id, data_inicio, data_fim, dias) VALUES (?, ?, ?, ?)',
                                       (funcionario_id, data_inicio.isoformat(), data_fim.isoformat(), dias))
                        conn.commit()
                        st.success("Férias marcadas.")

        ferias = pd.read_sql('''SELECT f.id, f.funcionario_id, fu.nome, f.data_inicio, f.data_fim FROM ferias f
                                JOIN funcionarios fu ON f.funcionario_id = fu.id ORDER BY f.data_inicio DESC''', conn)
        if not ferias.empty:
            st.dataframe(ferias)
            with st.expander("Editar / Apagar Férias"):
                for _, row in ferias.iterrows():
                    with st.form(f"editar_ferias_{row['id']}"):
                        st.markdown(f"**{row['nome']}**")
                        novo_inicio = st.date_input("Início", value=pd.to_datetime(row['data_inicio']))
                        novo_fim = st.date_input("Fim", value=pd.to_datetime(row['data_fim']))
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("Atualizar"):
                                if novo_fim <= novo_inicio:
                                    st.error("Data final deve ser posterior.")
                                else:
                                    dias = calcular_dias_uteis(novo_inicio, novo_fim)
                                    ok, dia_conflito = verificar_limite_ferias(conn, novo_inicio, novo_fim, row['funcionario_id'])
                                    if not ok:
                                        st.error(f"Conflito em {dia_conflito}.")
                                    else:
                                        cursor = conn.cursor()
                                        cursor.execute('UPDATE ferias SET data_inicio = ?, data_fim = ?, dias = ? WHERE id = ?',
                                                       (novo_inicio.isoformat(), novo_fim.isoformat(), dias, row['id']))
                                        conn.commit()
                                        st.success("Atualizado.")
                                        st.rerun()
                        with col2:
                            if st.form_submit_button("Apagar"):
                                cursor.execute('DELETE FROM ferias WHERE id = ?', (row['id'],))
                                conn.commit()
                                st.warning("Férias removidas.")
                                st.rerun()

with tab3:
    st.subheader("Relatórios")
    df = pd.read_sql('''SELECT fu.nome as Funcionário, f.data_inicio as Início, f.data_fim as Fim, f.dias as Dias
                        FROM ferias f JOIN funcionarios fu ON f.funcionario_id = fu.id
                        ORDER BY f.data_inicio''', conn)
    if not df.empty:
        st.dataframe(df)

        resumo = pd.read_sql('''SELECT fu.nome as Funcionário, fu.dias_ferias as "Disponível", 
                                COALESCE(SUM(f.dias), 0) as "Usado",
                                (fu.dias_ferias - COALESCE(SUM(f.dias), 0)) as "Restante"
                                FROM funcionarios fu LEFT JOIN ferias f ON fu.id = f.funcionario_id
                                GROUP BY fu.id''', conn)
        st.subheader("Resumo por Funcionário")
        st.dataframe(resumo)

# Fechar conexão
if conn:
    conn.close()
