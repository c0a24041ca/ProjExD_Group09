import os
import sys
import random
import pygame as pg

WIDTH = 1100
HEIGHT = 650
FPS = 60

# デバッグ：地面ラインを表示するなら True
DEBUG_DRAW_GROUND_LINE = True

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ステージ2へ移行するフレーム（仕様に明記が無いので仮定：25秒相当）
STAGE2_TMR = 1500  # 60FPS想定

# グローバル（現在ステージの接地Y）
GROUND_Y = HEIGHT - 60


# =========================
# クラス外関数（メモ準拠）
# =========================
def load_image(filename: str) -> pg.Surface:
    """
    画像読み込み（fig/filename -> filename の順に探す）
    ※displayが未生成のタイミングでも落ちないようにする
    """
    candidates = [os.path.join("fig", filename), filename]
    last_err = None
    for path in candidates:
        try:
            img = pg.image.load(path)
            # 画面が作られている時だけ convert_alpha する
            if pg.display.get_init() and pg.display.get_surface() is not None:
                img = img.convert_alpha()
            return img
        except Exception as e:
            last_err = e
    raise SystemExit(f"画像 '{filename}' の読み込みに失敗しました: {last_err}")

def check_bound(obj_rct: pg.Rect) -> tuple[bool, bool]:
    yoko, tate = True, True
    if obj_rct.left < 0 or WIDTH < obj_rct.right:
        yoko = False
    if obj_rct.top < 0 or HEIGHT < obj_rct.bottom:
        tate = False
    return yoko, tate


def clamp_in_screen(rect: pg.Rect) -> pg.Rect:
    rect.left = max(0, rect.left)
    rect.right = min(WIDTH, rect.right)
    rect.top = max(0, rect.top)
    rect.bottom = min(HEIGHT, rect.bottom)
    return rect


def get_ground_y() -> int:
    """
    現在ステージの地面Y
    """
    return GROUND_Y


def set_ground_y(v: int) -> None:
    global GROUND_Y
    GROUND_Y = v


def stage_params(stage: int) -> dict:
    """
    ステージごとの設定
    ※追加機能（遷移画面等）は入れない
    """
    if stage == 1:
        return {
            "bg_file": "bg_1.jpg",
            "bg_speed": 4,
            "enemy_speed": 5,
            "spawn_interval": 60,  # フレーム間隔
        }
    return {
        "bg_file": "bg_2.jpg",
        "bg_speed": 6,
        "enemy_speed": 5,
        "spawn_interval": 45,
    }


def should_switch_stage(tmr: int) -> bool:
    """
    ステージ2へ移行する条件（仕様が無いので仮定：一定時間）
    """
    return tmr >= STAGE2_TMR

#高柳変更
def spawn_enemy(enemies: pg.sprite.Group, stage: int) -> None:
    params = stage_params(stage)
    kind = random.choice(["ground", "air"])  # 地面敵 / 空中敵
    enemies.add(Enemy(stage=stage, kind=kind, speed=params["enemy_speed"]))




def detect_ground_y(bg_scaled: pg.Surface) -> int:
    """
    リサイズ済み背景から「暗くて横方向に均一な水平ライン」を推定し、
    その“1px下”を地面Yとして返す。

    根拠：
    - 横方向に広がる地面境界の線（黒系）を想定
    - mean(明るさ)が低く、std(ばらつき)が小さい行を優先
    """
    w, h = bg_scaled.get_size()

    # 検出範囲（下半分中心に探す）
    # 背景によってはここを広げると安定する
    y_start = int(h * 0.40)
    y_end = int(h * 0.90)

    x_step = 4  # 横は間引き（速度優先）
    best_y = int(h * 0.75)
    best_score = 10**18

    for y in range(y_start, y_end):
        s = 0.0
        s2 = 0.0
        n = 0
        for x in range(0, w, x_step):
            r, g, b, a = bg_scaled.get_at((x, y))
            # 近似輝度（一般的な重み）
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            s += lum
            s2 += lum * lum
            n += 1

        mean = s / n
        var = (s2 / n) - mean * mean
        std = (var ** 0.5) if var > 0 else 0.0

        # “暗い”＋“横一線で均一”を狙う
        score = mean + 0.3 * std

        if score < best_score:
            best_score = score
            best_y = y

    # 線の上に乗るとめり込むことがあるので1px下を床にする
    return min(h - 1, best_y + 1)


# =========================
# クラス（必要に応じて get_～ を用意）
# =========================
class Background:
    """
    背景を右→左へ強制スクロール（2枚並べてループ）
    """
    def __init__(self, bg_file: str, speed: int):
        raw = load_image(bg_file)
        self._img = pg.transform.smoothscale(raw, (WIDTH, HEIGHT))
        self._speed = speed
        self._x1 = 0
        self._x2 = WIDTH

        # 背景から地面Yを推定してグローバル更新
        set_ground_y(detect_ground_y(self._img))

    def update(self, screen: pg.Surface):
        self._x1 -= self._speed
        self._x2 -= self._speed

        if self._x1 <= -WIDTH:
            self._x1 = self._x2 + WIDTH
        if self._x2 <= -WIDTH:
            self._x2 = self._x1 + WIDTH

        screen.blit(self._img, (self._x1, 0))
        screen.blit(self._img, (self._x2, 0))

    def set_speed(self, v: int) -> None:
        self._speed = v

    def get_speed(self) -> int:
        return self._speed

    def get_image(self) -> pg.Surface:
        return self._img


class Bird(pg.sprite.Sprite):
    """
    プレイヤー：左右移動＋ジャンプ＋二段ジャンプ
    ※常に“地面に足がつく”＝接地時は ground_y に rect.bottom を合わせる
    """
    def __init__(self, num: int, xy: tuple[int, int]):
        super().__init__()
        img0 = pg.transform.rotozoom(load_image(f"{num}.png"), 0, 0.9)
        img = pg.transform.flip(img0, True, False)

        self._imgs = {+1: img, -1: img0}
        self._dir = +1

        # pygame互換（Group.draw用）
        self.image = self._imgs[self._dir]
        self.rect = self.image.get_rect()

        # 物理
        self._vx = 0
        self._vy = 0.0
        self._speed = 8
        self._gravity = 0.85
        self._jump_v0 = -15
        self._jump_count = 0
        self._max_jump = 2

        self.rect.center = xy
        self.rect.bottom = get_ground_y()

        # --- HP/無敵時間（追加） ---高柳
        self.hp = 100
        self._inv = 0   # 無敵フレーム（連続ダメ防止）


    def try_jump(self) -> None:
        if self._jump_count < self._max_jump:
            self._vy = self._jump_v0
            self._jump_count += 1

    def update(self, key_lst: list[bool], screen: pg.Surface):
        # 左右入力
        self._vx = 0
        if key_lst[pg.K_LEFT]:
            self._vx = -self._speed
            self._dir = -1
        if key_lst[pg.K_RIGHT]:
            self._vx = +self._speed
            self._dir = +1
        if self._inv > 0:
            self._inv -= 1


        # 横移動
        self.rect.x += self._vx
        self.rect = clamp_in_screen(self.rect)

        # 重力
        self._vy += self._gravity
        self.rect.y += int(self._vy)

        # 接地（背景に合わせた地面Y）
        gy = get_ground_y()
        if self.rect.bottom >= gy:
            self.rect.bottom = gy
            self._vy = 0.0
            self._jump_count = 0

        # 描画
        self.image = self._imgs[self._dir]
        screen.blit(self.image, self.rect)

    # getters（必要なものだけ）
    def get_rect(self) -> pg.Rect:
        return self.rect

    def get_jump_count(self) -> int:
        return self._jump_count

    def get_speed(self) -> int:
        return self._speed
    
    #高柳追加
    def take_damage(self, dmg: int) -> None:
        """無敵中でなければダメージを受ける"""
        if self._inv == 0:
            self.hp = max(0, self.hp - dmg)
            self._inv = 30  # 0.5秒くらい（60FPS想定）

    def get_vy(self) -> float:
        return self._vy

    def set_vy(self, v: float) -> None:
        self._vy = v


#変更高柳
class Enemy(pg.sprite.Sprite):
    """
    モブ敵（2パターン）
    - ground : 地面に沿って左へ流れる（ジャンプで踏める）
    - air    : 空中を左へ流れる（踏める）
    ステージ1: doragon1.png / gimen1.png
    ステージ2: doragon2.png / gimen2.png
    """
    def __init__(self, stage: int, kind: str = "ground", speed: int = 7):
        super().__init__()
        self.stage = stage
        self.kind = kind

        # ステージごとの画像を選ぶ（UFO/alienは使わない）
        if self.stage == 1:
            img_file = "gimen1.png" if self.kind == "ground" else "doragon1.png"
        else:
            img_file = "gimen2.png" if self.kind == "ground" else "doragon2.png"

        base = load_image(img_file)

        # サイズ調整（必要なら数字だけ変えてOK）
        scale = 0.25 if self.kind == "ground" else 0.25
        self.image = pg.transform.rotozoom(base, 0, scale)
        self.rect = self.image.get_rect()

        # 右端から左へ流れる（地面と平行）
        self.vx = -speed
        self.vy = 0
        self.rect.left = WIDTH + random.randint(0, 80)

        gy = get_ground_y()
        if self.kind == "ground":
            self.rect.bottom = gy
        else:
            y = gy - random.randint(120, 260)
            self.rect.bottom = max(40, y)

    def update(self):
        self.rect.move_ip(self.vx, self.vy)

        if (
            self.rect.right < -50 or
            self.rect.left > WIDTH + 50 or
            self.rect.top > HEIGHT + 50
        ):
            self.kill()





# =========================
# メイン
# =========================
def main():
    pg.display.set_caption("こうかとん横スクロール（ベース）")
    screen = pg.display.set_mode((WIDTH, HEIGHT))
    clock = pg.time.Clock()

   

    stage = 1
    params = stage_params(stage)

    bg = Background(params["bg_file"], params["bg_speed"])
    bird = Bird(3, (200, get_ground_y()))
    enemies = pg.sprite.Group()

    tmr = 0

    while True:
        key_lst = pg.key.get_pressed()

        for event in pg.event.get():
            if event.type == pg.QUIT:
                return 0
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    return 0
                if event.key == pg.K_UP:
                    bird.try_jump()

        # ステージ切替（全2ステージ）
        if stage == 1 and should_switch_stage(tmr):
            stage = 2
            params = stage_params(stage)
            bg = Background(params["bg_file"], params["bg_speed"])
            # bird を新しい地面Yへ合わせる（めり込み/浮きを防ぐ）
            bird.get_rect().bottom = get_ground_y()
            enemies.empty()  # ★ステージ1の敵を消して、以後は2の画像だけ出す



        # 敵生成：複数流入
        if tmr % params["spawn_interval"] == 0:
            spawn_enemy(enemies, stage)
            if random.random() < 0.30:
                spawn_enemy(enemies, stage)

        # 描画
        bg.update(screen)

        if DEBUG_DRAW_GROUND_LINE:
            pg.draw.line(screen, (0, 0, 0), (0, get_ground_y()), (WIDTH, get_ground_y()), 2)

        bird.update(key_lst, screen)
        enemies.update()

                # --- 敵との当たり判定 ---
        hits = pg.sprite.spritecollide(bird, enemies, False)
        for emy in hits:
            if bird.get_vy() > 0 and (bird.rect.bottom - emy.rect.top) <= 20:
                emy.kill()
                bird.set_vy(-12)
            else:
                return 0


        # HPが0ならゲーム終了（任意）
        if bird.hp <= 0:
            return 0

        enemies.draw(screen)


        pg.display.update()
        tmr += 1
        clock.tick(FPS)


if __name__ == "__main__":
    pg.init()
    main()
    pg.quit()
    sys.exit()
