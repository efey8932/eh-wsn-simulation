import pygame
import random
import math
import sys
import csv
import datetime

# ==========================================
# 1. TEMEL AYARLAR VE PARAMETRELER (BİLİMSEL MODEL)
# ==========================================
# Ekran Ayarları
WINDOW_WIDTH = 1350
WINDOW_HEIGHT = 750
PANEL_WIDTH = 400
PANEL_HEIGHT = 450
FPS = 60

# Simülasyon Parametreleri (Bilimsel RX/TX Dengesi)
NUM_NODES = 50
INITIAL_ENERGY = 65.0     # Başlangıç enerjisi
MAX_ENERGY = 100.0
COMM_RANGE = 180          # İletişim yarıçapı

# Enerji Katsayıları (Gerçekçi WSN Modeli - FAZ 2)
E_COMM_COEFF = 0.00004    # Mesafe tabanlı TX (Gönderim) maliyeti
ACTIVE_BASE_ENERGY = 0.1  # Temel TX (Gönderim) maliyeti
RX_BASE_ENERGY = 0.05     # Başkasının paketini alma/dinleme (RX) maliyeti
SLEEP_ENERGY = 0.012      # Boşta bekleme tüketimi
PACKET_GEN_INTERVAL = 150 # Her düğümün paket üretme periyodu (Frame cinsinden - FAZ 4)

# Güneş Enerjisi (Harvesting) Ayarları
HARVEST_RATE = 0.038      # Gündüzleri şarj olma hızı
CYCLE_DURATION = 300      # Bir tam gün-gece döngüsü (5 saniye)
MAX_SIM_TIME = 3000       # Otomatik bitiş süresi (50 saniye sürer)

# Renk Paleti (Modern & Karanlık Tema)
C_BG = (10, 15, 25)
C_PANEL_BG_NIGHT = (15, 20, 30)
C_PANEL_BG_DAY = (50, 80, 100)
C_TEXT = (240, 248, 255)
C_TEXT_DIM = (148, 163, 184)
C_BS = (56, 189, 248)       
C_HIGH_BATT = (34, 197, 94) 
C_MED_BATT = (234, 179, 8)  
C_LOW_BATT = (239, 68, 68)  
C_DEAD = (51, 65, 85)       
C_PACKET = (255, 255, 255)
C_BTN = (30, 41, 59)
C_BTN_HOVER = (51, 65, 85)
C_BAR_BG = (30, 41, 59)

# Durum Sabitleri
STATE_RUNNING = 0
STATE_PAUSED = 1
STATE_RESULTS = 2


def distance(pos1, pos2):
    return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))

# ==========================================
# 2. SINIFLAR (Buton, Paket, Düğüm)
# ==========================================
class Button:
    def __init__(self, x, y, w, h, text, font, bg_color=C_BTN, hover_color=C_BTN_HOVER, text_color=C_TEXT):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.font = font
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.is_hovered = False

    def draw(self, surface):
        color = self.hover_color if self.is_hovered else self.bg_color
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, (100, 116, 139), self.rect, width=2, border_radius=8)
        text_surf = self.font.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

    def check_hover(self, pos):
        self.is_hovered = self.rect.collidepoint(pos)

    def is_clicked(self, pos, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.rect.collidepoint(pos)
        return False

class Packet:
    def __init__(self, start_pos, end_pos, target_id, speed=12):
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.current_pos = list(start_pos)
        self.target_id = target_id  # FAZ 3: Paketin varacağı düğümün ID'si
        self.speed = speed
        self.progress = 0.0
        self.distance = distance(start_pos, end_pos)
        self.reached = False

    def move(self):
        if self.distance == 0:
            self.reached = True
            return
        
        self.progress += self.speed / self.distance
        if self.progress >= 1.0:
            self.progress = 1.0
            self.reached = True
            
        self.current_pos[0] = self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * self.progress
        self.current_pos[1] = self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * self.progress

    def draw(self, surface):
        pos = (int(self.current_pos[0]), int(self.current_pos[1]))
        pygame.draw.circle(surface, C_PACKET, pos, 3)

class Node:
    def __init__(self, id, x, y):
        self.id = id
        self.x = x
        self.y = y
        self.pos = (self.x, self.y)
        self.energy = INITIAL_ENERGY
        self.alive = True
        self.is_transmitting = False
        self.is_charging = False
        self.radar_radius = 0
        
        # FAZ 3 & 4: Kuyruk ve Zamanlayıcı Mimarisi
        self.queue = 0  # İletilmeyi bekleyen paket sayısı
        self.gen_timer = random.randint(0, PACKET_GEN_INTERVAL)

    def get_color(self):
        if not self.alive: return C_DEAD
        if self.energy > 60: return C_HIGH_BATT
        elif self.energy > 25: return C_MED_BATT
        else: return C_LOW_BATT

    def update(self, is_day, harvest_enabled):
        if not self.alive: return
        
        self.is_transmitting = False
        self.is_charging = False
        
        # Enerji Hasadı
        if harvest_enabled and is_day and self.energy < MAX_ENERGY:
            self.energy += HARVEST_RATE
            self.is_charging = True
            if self.energy > MAX_ENERGY:
                self.energy = MAX_ENERGY
                
        # Uyku/Boşta tüketimi
        self.energy -= SLEEP_ENERGY
        
        # Zamanlayıcı bazlı veri üretimi (Düzenli sensör okuması)
        self.gen_timer += 1
        if self.gen_timer >= PACKET_GEN_INTERVAL:
            self.gen_timer = 0
            self.queue += 1  # Kendi ürettiği veriyi kuyruğa ekle
            
        if self.energy <= 0:
            self.energy = 0
            self.alive = False

    def draw(self, surface):
        color = self.get_color()
        
        if self.alive and self.is_transmitting:
            self.radar_radius += 3
            if self.radar_radius > 25:
                self.radar_radius = 5
            pygame.draw.circle(surface, color, self.pos, int(self.radar_radius), 1)

        pygame.draw.circle(surface, color, self.pos, 6)
        
        if self.alive:
            pygame.draw.arc(surface, (255,255,255), (self.x-10, self.y-10, 20, 20), 
                            math.pi/2, math.pi/2 + (2*math.pi * (self.energy/MAX_ENERGY)), 2)
            if self.is_charging:
                pygame.draw.circle(surface, (255, 230, 0), (self.x+6, self.y-6), 3)

# ==========================================
# 3. SİMÜLASYON YÖNETİCİSİ
# ==========================================
class SimulationEngine:
    def __init__(self, name, harvest_enabled, day_ratio, master_positions):
        self.name = name
        self.harvest_enabled = harvest_enabled
        self.day_ratio = day_ratio  
        
        self.width = PANEL_WIDTH
        self.height = PANEL_HEIGHT
        self.surface = pygame.Surface((self.width, self.height))
        self.base_station = (self.width // 2, 40)
        
        # FAZ 1: Ortak ağ topolojisini (Evreni) kullan
        self.nodes = [Node(i, master_positions[i][0], master_positions[i][1]) for i in range(NUM_NODES)]
        self.packets = []
        
        self.successful_packets = 0 # Merkeze sağ salim ulaşan paketler (Throughput)
        self.time_step = 0
        self.is_day = False
        self.bg_color = C_PANEL_BG_NIGHT

    def update(self):
        self.time_step += 1
        
        cycle_pos = (self.time_step % CYCLE_DURATION) / CYCLE_DURATION
        self.is_day = cycle_pos < self.day_ratio

        if self.harvest_enabled:
            transition_speed = 0.05
            if cycle_pos < transition_speed:
                self.bg_color = lerp_color(C_PANEL_BG_NIGHT, C_PANEL_BG_DAY, cycle_pos / transition_speed)
            elif self.day_ratio < cycle_pos < (self.day_ratio + transition_speed):
                self.bg_color = lerp_color(C_PANEL_BG_DAY, C_PANEL_BG_NIGHT, (cycle_pos - self.day_ratio) / transition_speed)
            elif self.is_day:
                self.bg_color = C_PANEL_BG_DAY
            else:
                self.bg_color = C_PANEL_BG_NIGHT
        else:
            self.bg_color = C_PANEL_BG_NIGHT 

        alive_nodes = [n for n in self.nodes if n.alive]
        
        # FAZ 2 & 3: Yoldaki Paketleri İşle (RX Maliyeti ve Röleleme)
        for p in self.packets:
            p.move()
            if p.reached:
                if p.target_id == 'BS':
                    self.successful_packets += 1 # Paket başaryla merkeze ulaştı
                else:
                    # Paket aracı bir düğüme ulaştı, RX enerjisini düş ve kuyruğa ekle
                    target_node = next((n for n in self.nodes if n.id == p.target_id), None)
                    if target_node and target_node.alive:
                        target_node.energy -= RX_BASE_ENERGY
                        target_node.queue += 1 
                        if target_node.energy <= 0:
                            target_node.energy = 0
                            target_node.alive = False

        self.packets = [p for p in self.packets if not p.reached]

        # FAZ 3: Düğüm Mantığı ve Greedy Multi-Hop Aktarımı
        for node in self.nodes:
            node.update(self.is_day, self.harvest_enabled)
            
            # Eğer kuyrukta paket varsa ve hayattaysa, en uygun komşuya yolla
            if node.alive and node.queue > 0:
                node.is_transmitting = True
                
                target_pos = self.base_station
                target_id = 'BS'
                best_dist = distance(node.pos, self.base_station)
                
                # Açgözlü (Greedy) Yönlendirme: Merkeze benden daha yakın en iyi komşuyu bul
                for other in alive_nodes:
                    if other.id != node.id:
                        d_ij = distance(node.pos, other.pos)
                        d_other_bs = distance(other.pos, self.base_station)
                        if d_ij < COMM_RANGE and d_other_bs < best_dist:
                            best_dist = d_other_bs
                            target_pos = other.pos
                            target_id = other.id
                
                # TX Enerjisini Düş
                actual_dist = distance(node.pos, target_pos)
                cost = ACTIVE_BASE_ENERGY + (actual_dist**2 * E_COMM_COEFF)
                node.energy -= cost
                
                node.queue -= 1 # Kuyruktan 1 paketi fırlattık
                self.packets.append(Packet(node.pos, target_pos, target_id))

    def draw(self, font_small, font_title):
        self.surface.fill(self.bg_color)
        
        pygame.draw.rect(self.surface, (100, 116, 139), self.surface.get_rect(), 2)

        title_surf = font_title.render(self.name, True, C_TEXT)
        self.surface.blit(title_surf, (15, 10))

        if self.harvest_enabled:
            cycle_pos = (self.time_step % CYCLE_DURATION) / CYCLE_DURATION
            sun_x = int(self.width * cycle_pos)
            sun_y = 60 + int(math.sin(cycle_pos * math.pi) * 20)
            if self.is_day:
                pygame.draw.circle(self.surface, (255, 200, 0), (sun_x, sun_y), 15)
            else:
                pygame.draw.circle(self.surface, (200, 200, 220), (sun_x, sun_y), 12)

        for p in self.packets:
            pygame.draw.line(self.surface, (255,255,255, 40), p.start_pos, p.current_pos, 1)
            p.draw(self.surface)

        pygame.draw.rect(self.surface, C_BS, (self.base_station[0]-12, self.base_station[1]-12, 24, 24))
        
        for node in self.nodes:
            node.draw(self.surface)

        alive_count = sum(1 for n in self.nodes if n.alive)
        stats = [
            f"Canlı Düğüm: {alive_count} / {NUM_NODES}",
            f"Sağlık Oranı: %{int(alive_count/NUM_NODES*100)}",
            f"Merkeze Ulaşan Veri: {self.successful_packets}"
        ]
        y_off = self.height - 55
        for txt in stats:
            surf = font_small.render(txt, True, C_TEXT_DIM)
            self.surface.blit(surf, (15, y_off))
            y_off += 18

    def get_survival_rate(self):
        return sum(1 for n in self.nodes if n.alive) / NUM_NODES * 100

# ==========================================
# 4. CSV ÇIKTI FONKSİYONU (FAZ 5)
# ==========================================
def export_to_csv(engines):
    try:
        filename = f"WSN_Akademik_Sonuclar_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(filename, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Simulasyon Modeli", "Hayatta Kalma Orani (%)", "Kalan Canli Dugum", "Merkeze Ulasan Paket (Throughput)"])
            
            for eng in engines:
                survival = eng.get_survival_rate()
                alive = sum(1 for n in eng.nodes if n.alive)
                writer.writerow([eng.name, survival, alive, eng.successful_packets])
                
        print(f"\n[BAŞARILI] Akademik simülasyon sonuçları kaydedildi: {filename}")
        return True
    except Exception as e:
        print(f"\n[HATA] CSV oluşturulurken bir hata oluştu: {e}")
        return False

# ==========================================
# 5. SONUÇ GRAFİĞİ ÇİZİMİ
# ==========================================
def draw_results(screen, font_large, font_medium, font_small, engines, csv_saved):
    screen.fill(C_BG)
    
    title = font_large.render("Ağ Ömrü Karşılaştırması ve Proje Sonuçları", True, (245, 158, 11))
    screen.blit(title, (50, 40))
    pygame.draw.line(screen, (56, 189, 248), (50, 80), (600, 80), 3)
    
    purpose_rect = pygame.Rect(50, 100, WINDOW_WIDTH - 100, 70)
    pygame.draw.rect(screen, (15, 23, 42), purpose_rect, border_radius=8)
    pygame.draw.rect(screen, (56, 189, 248), purpose_rect, width=1, border_radius=8)
    
    purpose_title = font_medium.render("Projenin Amacı (Bilimsel RX/TX Routing Modeli):", True, (56, 189, 248))
    purpose_text = font_small.render("Gerçek bir Multi-Hop mimarisinde darboğaz düğümlerini gözlemlemek ve güneş enerjisinin ağ güvenilirliğini nasıl artırdığını ispatlamak.", True, C_TEXT)
    screen.blit(purpose_title, (70, 110))
    screen.blit(purpose_text, (70, 135))

    rect = pygame.Rect(50, 190, WINDOW_WIDTH - 100, 450)
    pygame.draw.rect(screen, (15, 23, 42), rect, border_radius=10)
    pygame.draw.rect(screen, (51, 65, 85), rect, width=2, border_radius=10)

    colors = [(148, 163, 184), (56, 189, 248), (250, 204, 21)] 
    start_y = 220
    max_bar_width = 480
    
    standart_survival = engines[0].get_survival_rate()

    for i, eng in enumerate(engines):
        survival = eng.get_survival_rate()
        alive_nodes = sum(1 for n in eng.nodes if n.alive)
        
        lbl = font_medium.render(eng.name, True, C_TEXT)
        screen.blit(lbl, (80, start_y + 15))
        
        bar_bg = pygame.Rect(350, start_y + 10, max_bar_width, 40)
        pygame.draw.rect(screen, C_BAR_BG, bar_bg, border_radius=6)
        
        fill_width = int((survival / 100.0) * max_bar_width)
        if fill_width > 0:
            bar_fill = pygame.Rect(350, start_y + 10, fill_width, 40)
            pygame.draw.rect(screen, colors[i], bar_fill, border_radius=6)
            
        val_txt = font_medium.render(f"%{int(survival)} ({alive_nodes}/{NUM_NODES} Canlı)", True, (10, 15, 25) if fill_width > 200 else C_TEXT)
        txt_x = 350 + fill_width - val_txt.get_width() - 10 if fill_width > 200 else 350 + fill_width + 10
        screen.blit(val_txt, (txt_x, start_y + 18))
        
        # Başarılı Paket (Throughput) Bilgisi
        if i > 0:
            tasarruf_nodes = alive_nodes - sum(1 for n in engines[0].nodes if n.alive)
            tasarruf_txt = font_small.render(f"+{tasarruf_nodes} Düğüm | Başarılı Teslimat: {eng.successful_packets} Paket", True, (34, 197, 94))
            screen.blit(tasarruf_txt, (850, start_y + 20))
        else:
            base_txt = font_small.render(f"Referans Model | Başarılı Teslimat: {eng.successful_packets} Paket", True, C_TEXT_DIM)
            screen.blit(base_txt, (850, start_y + 20))
        
        start_y += 90

    desc = font_small.render("Merkeze yakın 'Darboğaz (Bottleneck)' düğümleri başkalarının paketlerini taşıdığı (RX Maliyeti) için en hızlı ölen düğümlerdir.", True, C_TEXT_DIM)
    desc2 = font_small.render("Enerji hasadı (EH-WSN) bu yükü tolere ederek ağın kopmasını engeller ve merkeze ulaşan veriyi (Throughput) katlayarak artırır.", True, C_TEXT_DIM)
    
    desc_rect = pygame.Rect(80, start_y + 20, WINDOW_WIDTH - 160, 80)
    pygame.draw.rect(screen, (30, 41, 59), desc_rect, border_radius=8)
    pygame.draw.rect(screen, (245, 158, 11), desc_rect, width=1, border_radius=8) 
    
    screen.blit(desc, (100, start_y + 35))
    screen.blit(desc2, (100, start_y + 60))

    if csv_saved:
        saved_txt = font_medium.render("✓ Sonuçlar CSV Olarak Kaydedildi!", True, (34, 197, 94))
        screen.blit(saved_txt, (1000, 50))

# ==========================================
# 6. ANA DÖNGÜ (MAIN)
# ==========================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("EH-WSN Karşılaştırmalı Akademik Simülasyon (RX/TX Routing)")
    clock = pygame.time.Clock()

    font_large = pygame.font.SysFont("segoeui, arial", 32, bold=True)
    font_medium = pygame.font.SysFont("segoeui, arial", 18, bold=True)
    font_small = pygame.font.SysFont("segoeui, arial", 14)

    # FAZ 1: Adil yarış için sabit topoloji (Evren) oluştur
    master_positions = [(random.randint(20, PANEL_WIDTH - 20), random.randint(80, PANEL_HEIGHT - 20)) for _ in range(NUM_NODES)]

    engines = [
        SimulationEngine("Standart WSN (Statik Pilli)", harvest_enabled=False, day_ratio=0.5, master_positions=master_positions),
        SimulationEngine("EH-WSN (Kış / Uzun Gece)", harvest_enabled=True, day_ratio=0.25, master_positions=master_positions),
        SimulationEngine("EH-WSN (Yaz / Uzun Gündüz)", harvest_enabled=True, day_ratio=0.75, master_positions=master_positions)
    ]

    btn_y = 620
    btn_play_pause = Button(WINDOW_WIDTH//2 - 220, btn_y, 200, 50, "Durdur (Pause)", font_medium)
    btn_results = Button(WINDOW_WIDTH//2 + 20, btn_y, 200, 50, "Sonuçları Göster", font_medium)
    
    # Sonuç Ekranı Butonları
    btn_restart = Button(WINDOW_WIDTH//2 - 220, 660, 200, 50, "Yeniden Başlat", font_medium)
    btn_csv = Button(WINDOW_WIDTH//2 + 20, 660, 200, 50, "CSV İndir (Rapor)", font_medium, bg_color=(34, 197, 94), hover_color=(21, 128, 61), text_color=(255, 255, 255))

    state = STATE_RUNNING
    global_time = 0
    csv_saved = False

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
            if state in [STATE_RUNNING, STATE_PAUSED]:
                if btn_play_pause.is_clicked(mouse_pos, event):
                    if state == STATE_RUNNING:
                        state = STATE_PAUSED
                        btn_play_pause.text = "Devam Et (Play)"
                    else:
                        state = STATE_RUNNING
                        btn_play_pause.text = "Durdur (Pause)"
                
                if btn_results.is_clicked(mouse_pos, event):
                    state = STATE_RESULTS
                    
            elif state == STATE_RESULTS:
                if btn_restart.is_clicked(mouse_pos, event):
                    # Yeni bir evren (harita) oluştur ve sıfırla
                    master_positions = [(random.randint(20, PANEL_WIDTH - 20), random.randint(80, PANEL_HEIGHT - 20)) for _ in range(NUM_NODES)]
                    engines = [
                        SimulationEngine("Standart WSN (Statik Pilli)", harvest_enabled=False, day_ratio=0.5, master_positions=master_positions),
                        SimulationEngine("EH-WSN (Kış / Uzun Gece)", harvest_enabled=True, day_ratio=0.25, master_positions=master_positions),
                        SimulationEngine("EH-WSN (Yaz / Uzun Gündüz)", harvest_enabled=True, day_ratio=0.75, master_positions=master_positions)
                    ]
                    state = STATE_RUNNING
                    global_time = 0
                    csv_saved = False
                    btn_play_pause.text = "Durdur (Pause)"
                
                if btn_csv.is_clicked(mouse_pos, event) and not csv_saved:
                    csv_saved = export_to_csv(engines)

        if state == STATE_RUNNING:
            global_time += 1
            for eng in engines:
                eng.update()
                
            if global_time >= MAX_SIM_TIME:
                state = STATE_RESULTS

        if state in [STATE_RUNNING, STATE_PAUSED]:
            screen.fill(C_BG)
            
            title_text = font_large.render("Güneş Enerjisi Hasatlı Sensör Ağları Performans Analizi", True, C_TEXT)
            screen.blit(title_text, (WINDOW_WIDTH//2 - title_text.get_width()//2, 30))
            
            spacing = 30
            start_x = (WINDOW_WIDTH - (3 * PANEL_WIDTH + 2 * spacing)) // 2
            
            for i, eng in enumerate(engines):
                eng.draw(font_small, font_medium)
                panel_x = start_x + i * (PANEL_WIDTH + spacing)
                panel_y = 120
                screen.blit(eng.surface, (panel_x, panel_y))
                
            pygame.draw.rect(screen, (15, 23, 42), (0, 600, WINDOW_WIDTH, 150))
            pygame.draw.line(screen, (51, 65, 85), (0, 600), (WINDOW_WIDTH, 600), 2)
            
            btn_play_pause.check_hover(mouse_pos)
            btn_play_pause.draw(screen)
            
            btn_results.check_hover(mouse_pos)
            btn_results.draw(screen)
            
            time_txt = font_medium.render(f"Simülasyon Zamanı: {global_time} / {MAX_SIM_TIME}", True, C_TEXT_DIM)
            screen.blit(time_txt, (WINDOW_WIDTH//2 - time_txt.get_width()//2, 690))

        elif state == STATE_RESULTS:
            draw_results(screen, font_large, font_medium, font_small, engines, csv_saved)
            
            btn_restart.check_hover(mouse_pos)
            btn_restart.draw(screen)
            
            btn_csv.check_hover(mouse_pos)
            btn_csv.draw(screen)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()