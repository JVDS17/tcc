# Crawler ORIGINAL usado na coleta de 30/03/2026 a 19/04/2026.
# Única alteração em relação ao código executado: a chave de acesso do feed de
# tempo real passou a ser lida da variável de ambiente PBH_RT_ACCESSKEY.
#
# Funcionamento: baixa o GTFS estático da BHTRANS, consulta o feed GTFS-Realtime
# (VehiclePositions) a cada 20 s durante sessões de 12 h e grava as posições das
# linhas-alvo em abas de uma planilha do Google Sheets (via Service Account).
# Requer: requests, pandas, pytz, gspread, google-auth, gtfs-realtime-bindings
# e um arquivo credentials.json da Service Account (NUNCA versionar esse arquivo).
import requests
import time
import pandas as pd
import zipfile
import os
import pytz
import gspread
from google.transit import gtfs_realtime_pb2
from datetime import datetime
from google.oauth2.service_account import Credentials

# ==============================================================================
# CONFIGURAÇÕES DO USUÁRIO (VERSÃO DESKTOP 12H + FUSO BRASÍLIA)
# ==============================================================================
# 1. Coloque o arquivo 'credentials.json' na mesma pasta deste script.
# 2. Compartilhe sua planilha com o e-mail do Service Account (Editor).
ARQUIVO_CREDENCIAIS = 'credentials.json' 
NOME_PLANILHA = "Monitoramento Transporte BH"
LINHAS_ALVO = ["4033", "4110"] # Adicione as linhas aqui
DURACAO_HORAS = 12             # Tempo total que o script ficará rodando
INTERVALO_SEGUNDOS = 20        # Tempo entre cada captura

# URLs OFICIAIS PBH
# A chave de acesso do feed foi retirada do código para não ficar publicada no
# repositório. Defina a variável de ambiente PBH_RT_ACCESSKEY antes de rodar.
GTFS_RT_URL = "http://realtime4.mobilibus.com/web/4ch6j/vehicle-positions?accesskey=" + os.environ.get("PBH_RT_ACCESSKEY", "")
GTFS_ZIP_URL = "https://s3.amazonaws.com/mobilibus-uploads/gtfs/GTFSBHTRANS.zip"

class BHTrajectory12hFuso:
    def __init__(self, target_lines, spreadsheet_name):
        self.target_lines = target_lines
        self.spreadsheet_name = spreadsheet_name
        self.route_id_to_name = {}
        self.trip_to_departure = {}
        self.sheets_by_line = {}
        self.sh = None
        self.timezone = pytz.timezone('America/Sao_Paulo') # Fuso de Brasília (GMT-3)

    def setup_google_sheets(self):
        """Autentica e conecta com o Google Sheets usando Service Account."""
        print(f"[{datetime.now(self.timezone).strftime('%H:%M:%S')}] 🔐 Conectando ao Google Sheets...")
        
        if not os.path.exists(ARQUIVO_CREDENCIAIS):
            print(f"❌ Erro: Arquivo '{ARQUIVO_CREDENCIAIS}' não encontrado na pasta.")
            return False
            
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(ARQUIVO_CREDENCIAIS, scopes=scopes)
        gc = gspread.authorize(creds)

        try:
            self.sh = gc.open(self.spreadsheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"⚠️ Planilha '{self.spreadsheet_name}' não encontrada. Criando...")
            self.sh = gc.create(self.spreadsheet_name)

        # Cabeçalho padrão
        cabecalho = ["Timestamp (Brasília)", "Linha_Identificada", "Veículo", "Trip_ID", "Saída_Terminal", "Lat", "Lon", "Velocidade_KMH"]
        
        # Prepara abas individuais para cada linha
        for linha in self.target_lines:
            try:
                ws = self.sh.worksheet(linha)
            except gspread.exceptions.WorksheetNotFound:
                print(f"📝 Criando aba para a linha '{linha}'...")
                ws = self.sh.add_worksheet(title=linha, rows="10000", cols="10")
            
            if not ws.get_all_values():
                ws.append_row(cabecalho)
            self.sheets_by_line[linha] = ws
            
        print(f"✅ Conectado ao Google Sheets e abas preparadas!")
        return True

    def load_gtfs_static(self):
        """Mapeia horários e lida com variações de nomes de rotas."""
        print(f"[{datetime.now(self.timezone).strftime('%H:%M:%S')}] 📂 Carregando base de dados da PBH (GTFS)...")
        try:
            r = requests.get(GTFS_ZIP_URL, timeout=30)
            with open("gtfs_bh.zip", "wb") as f: f.write(r.content)

            with zipfile.ZipFile("gtfs_bh.zip") as z:
                with z.open('routes.txt') as f:
                    routes_df = pd.read_csv(f, dtype={'route_id': str, 'route_short_name': str})
                    # Mapeia variações (ex: 8208 ou 82080)
                    relevant = routes_df[
                        routes_df['route_short_name'].isin(self.target_lines) |
                        routes_df['route_short_name'].apply(lambda x: any(l in str(x) for l in self.target_lines))
                    ]
                    # Cria mapeamento de route_id para o nome simplificado da linha alvo
                    for _, row in relevant.iterrows():
                        for target in self.target_lines:
                            if target in str(row['route_short_name']):
                                self.route_id_to_name[row['route_id']] = target
                                break
                    
                    target_ids = set(self.route_id_to_name.keys())

                with z.open('trips.txt') as f:
                    trips_df = pd.read_csv(f, dtype={'route_id': str, 'trip_id': str})
                    valid_trips = set(trips_df[trips_df['route_id'].isin(target_ids)]['trip_id'])

                with z.open('stop_times.txt') as f:
                    stop_times = pd.read_csv(f, usecols=['trip_id', 'departure_time', 'stop_sequence'], dtype={'trip_id': str})
                    departures = stop_times[(stop_times['trip_id'].isin(valid_trips)) & (stop_times['stop_sequence'] == 1)]
                    self.trip_to_departure = departures.set_index('trip_id')['departure_time'].to_dict()
            print(f"✅ Mapeamento concluído.")
        except Exception as e:
            print(f"⚠️ Erro ao carregar GTFS: {e}")

    def fetch_realtime(self):
        """Busca GPS e captura dados para as abas correspondentes."""
        try:
            response = requests.get(GTFS_RT_URL, timeout=15)
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)

            batch_data = {linha: [] for linha in self.target_lines}
            now_bh = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")
            found_count = 0

            for entity in feed.entity:
                if entity.HasField('vehicle'):
                    v = entity.vehicle
                    line_name = self.route_id_to_name.get(v.trip.route_id)

                    # Tenta capturar pelo Trip_ID se o route_id falhar
                    if not line_name:
                        for target in self.target_lines:
                            if v.trip.trip_id.startswith(target):
                                line_name = target
                                break

                    if line_name in batch_data:
                        found_count += 1
                        departure = self.trip_to_departure.get(v.trip.trip_id, "Horário não disponível")
                        batch_data[line_name].append([
                            now_bh, line_name, v.vehicle.id, v.trip.trip_id,
                            departure, v.position.latitude, v.position.longitude,
                            round(v.position.speed * 3.6, 2) if v.position.speed else 0
                        ])
            
            # Envia para as abas
            for linha, rows in batch_data.items():
                if rows:
                    try:
                        self.sheets_by_line[linha].append_rows(rows)
                    except Exception as e:
                        print(f"\n⚠️ Erro ao enviar dados da linha {linha} (tentando reconectar): {e}")
                        self.setup_google_sheets() # Tenta reconectar se a API do Google falhar
            
            return found_count
        except Exception as e:
            print(f"\n❌ Erro na captura de tempo real: {e}")
            return 0

    def start(self, interval=20, duration_hours=12):
        if not self.setup_google_sheets(): return
        self.load_gtfs_static()
        
        total_loops = int((duration_hours * 3600) / interval)
        print(f"\n🚀 Iniciando Monitoramento de {duration_hours}h para: {', '.join(self.target_lines)}")
        print(f"⏰ Horário de Brasília (GMT-3) ativo.")
        
        for i in range(total_loops):
            count = self.fetch_realtime()
            if count > 0:
                print(f"[{datetime.now(self.timezone).strftime('%H:%M:%S')}] ✅ {count} ônibus enviados para as abas.")
            else:
                print(f"[{datetime.now(self.timezone).strftime('%H:%M:%S')}] ⏳ Buscando ônibus...", end='\r')
            time.sleep(interval)
            
        print(f"\n✅ Monitoramento de {duration_hours}h finalizado com sucesso!")

# --- EXECUÇÃO ---
if __name__ == "__main__":
    crawler = BHTrajectory12hFuso(LINHAS_ALVO, NOME_PLANILHA)
    # Roda pela duração configurada (padrão 12h)
    crawler.start(interval=INTERVALO_SEGUNDOS, duration_hours=DURACAO_HORAS)