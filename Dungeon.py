import os
import sys
import random
import pygame as pg
import math

WIDTH = 1100
HEIGHT = 650
FPS = 60

DEBUG_DRAW_GROUND_LINE = True

os.chdir(os.path.dirname(os.path.abspath(__file__)))

STAGE2_TMR = 1500
BOSS_TMR = 1200

GROUND_Y = HEIGHT - 60

# ★ 足元補正値
FOOT_OFFSET_BIRD = 10
FOOT_OFFSET_ENEMY = 5
FOOT_OFFSET_BOSS = 8


# =========================
# 共通関数
# =========================
def load_image(filename: str) -> pg.Surface:
    candidates = [os.path.join("fig", filename), filename]
    for path in candidates:
        try:
            return pg.image.load(path).convert_alpha()
        except:
            pass
    raise SystemExit(f"画像 {filename} の読み込みに失敗しました")


def clamp_in_screen(rect: pg.Rect) -> pg.Rect:
    rect.left = max(0, rect.left)
    rect.right = min(WIDTH, rect.right)
    rect.top = max(0, rect.top)
    rect.bottom = min(HEIGHT, rect.bottom)
    return rect


def get_ground_y() -> int:
    return GROUND_Y


def set_ground_y(v: int) -> None:
    global GROUND_Y
    GROUND_Y = v


def stage_params(stage: int) -> dict:
    if stage == 1:
        return {"bg_file": "bg_1.jpg", "bg_speed": 4, "enemy_speed": 7, "spawn_interval": 60}
    return {"bg_file": "bg_2.jpg", "bg_speed": 6, "enemy_speed": 9, "spawn_interval": 45}


def should_switch_stage(tmr: int) -> bool:
    return tmr >= STAGE2_TMR


def spawn_enemy(enemies, stage):
    enemies.add(Enemy(stage))


def detect_ground_y(bg_scaled: pg.Surface) -> int:
    w, h = bg_scaled.get_size()
    best_y = int(h * 0.75)
    best_score = 10**18
    for y in range(int(h * 0.4), int(h * 0.9)):
        s = s2 = n = 0
        for x in range(0, w, 4):
            r, g, b, a = bg_scaled.get_at((x, y))
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            s += lum
            s2 += lum * lum
            n += 1
        mean = s / n
        var = s2 / n - mean * mean
        std = math.sqrt(var) if var > 0 else 0
        score = mean + 0.3 * std
        if score < best_score:
            best_score = score
            best_y = y
    return min(h - 1, best_y + 1)


# =========================
# クラス
# =========================
class Background:
    def __init__(self, bg_file: str, speed: int):
        raw = load_image(bg_file)
        self._img = pg.transform.smoothscale(raw, (WIDTH, HEIGHT))
        self._speed = speed
        self._x1 = 0
        self._x2 = WIDTH
        set_ground_y(detect_ground_y(self._img))

    def update(self, screen):
        self._x1 -= self._speed
        self._x2 -= self._speed
        if self._x1 <= -WIDTH:
            self._x1 = self._x2 + WIDTH
        if self._x2 <= -WIDTH:
            self._x2 = self._x1 + WIDTH
        screen.blit(self._img, (self._x1, 0))
        screen.blit(self._img, (self._x2, 0))

    def set_speed(self, v: int):
        self._speed = v


class Bird(pg.sprite.Sprite):
    def __init__(self, num, xy):
        super().__init__()
        img0 = pg.transform.rotozoom(load_image(f"{num}.png"), 0, 0.9)
        img = pg.transform.flip(img0, True, False)
        self._imgs = {+1: img, -1: img0}
        self._dir = +1
        self.image = self._imgs[self._dir]
        self.rect = self.image.get_rect()

        self._vx = 0
        self._vy = 0
        self._speed = 8
        self._gravity = 0.85
        self._jump_v0 = -15
        self._jump_count = 0
        self._max_jump = 2

        self.rect.center = xy
        self.rect.bottom = get_ground_y() + FOOT_OFFSET_BIRD

    def try_jump(self):
        if self._jump_count < self._max_jump:
            self._vy = self._jump_v0
            self._jump_count += 1

    def update(self, key_lst, screen):
        self._vx = 0
        if key_lst[pg.K_LEFT]:
            self._vx = -self._speed
            self._dir = -1
        if key_lst[pg.K_RIGHT]:
            self._vx = self._speed
            self._dir = +1

        self.rect.x += self._vx
        self.rect = clamp_in_screen(self.rect)

        self._vy += self._gravity
        self.rect.y += int(self._vy)

        if self.rect.bottom >= get_ground_y() + FOOT_OFFSET_BIRD:
            self.rect.bottom = get_ground_y() + FOOT_OFFSET_BIRD
            self._vy = 0
            self._jump_count = 0

        self.image = self._imgs[self._dir]
        screen.blit(self.image, self.rect)

    def get_vy(self):
        return self._vy


class Enemy(pg.sprite.Sprite):
    def __init__(self, stage):
        super().__init__()
        self._speed = stage_params(stage)["enemy_speed"]
        self.image = pg.Surface((50, 50))
        self.image.fill((230, 70, 70))
        self.rect = self.image.get_rect()
        self.rect.left = WIDTH + random.randint(0, 150)
        self.rect.bottom = get_ground_y() + FOOT_OFFSET_ENEMY

    def update(self):
        self.rect.x -= self._speed
        self.rect.bottom = get_ground_y() + FOOT_OFFSET_ENEMY
        if self.rect.right < 0:
            self.kill()


class Boss(pg.sprite.Sprite):
    def __init__(self):
        super().__init__()

        self.base_image = pg.transform.smoothscale(
            load_image("zerueru1.png"), (200, 200)
        )
        self.hit_image = self.base_image.copy()
        self.hit_image.fill((255, 80, 80), special_flags=pg.BLEND_RGBA_MULT)

        self.image = self.base_image
        self.rect = self.image.get_rect()
        self.rect.centerx = WIDTH // 2
        self.rect.bottom = get_ground_y() + FOOT_OFFSET_BOSS

        self._vx = random.choice([-4, 4])
        self._vy = 0
        self._gravity = 0.8
        self._jump_v0 = -14

        self._action_tmr = 0
        self._next_action = random.randint(60, 120)

        self.hit_timer = 0

    def update(self):
        self._action_tmr += 1
        if self._action_tmr >= self._next_action:
            self._action_tmr = 0
            self._next_action = random.randint(60, 120)
            self._vx = random.choice([-4, 4])
            if random.random() < 0.4 and self.rect.bottom >= get_ground_y() + FOOT_OFFSET_BOSS:
                self._vy = self._jump_v0

        self.rect.x += self._vx
        if self.rect.left <= 80 or self.rect.right >= WIDTH - 80:
            self._vx *= -1

        self._vy += self._gravity
        self.rect.y += int(self._vy)

        if self.rect.bottom >= get_ground_y() + FOOT_OFFSET_BOSS:
            self.rect.bottom = get_ground_y() + FOOT_OFFSET_BOSS
            self._vy = 0

        if self.hit_timer > 0:
            self.hit_timer -= 1

        self.image = self.hit_image if self.hit_timer > 0 else self.base_image

    def on_hit(self):
        self.hit_timer = 10

    def draw(self, screen):
        screen.blit(self.image, self.rect)


# =========================
# メイン
# =========================
def main():
    pg.display.set_caption("こうかとんダンジョン")
    screen = pg.display.set_mode((WIDTH, HEIGHT))
    clock = pg.time.Clock()

    stage = 1
    params = stage_params(stage)
    bg = Background(params["bg_file"], params["bg_speed"])
    bird = Bird(3, (200, get_ground_y()))
    enemies = pg.sprite.Group()

    boss = None
    boss_active = False
    tmr = 0

    while True:
        key_lst = pg.key.get_pressed()

        for event in pg.event.get():
            if event.type == pg.QUIT:
                return
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    return
                if event.key == pg.K_UP:
                    bird.try_jump()

        if stage == 1 and should_switch_stage(tmr):
            stage = 2
            params = stage_params(stage)
            bg = Background(params["bg_file"], params["bg_speed"])
            bird.rect.bottom = get_ground_y() + FOOT_OFFSET_BIRD
            tmr = 0

        if stage == 2 and not boss_active and tmr >= BOSS_TMR:
            boss_active = True
            bg.set_speed(0)
            enemies.empty()
            boss = Boss()

        if not boss_active:
            if tmr % params["spawn_interval"] == 0:
                spawn_enemy(enemies, stage)

        bg.update(screen)

        if DEBUG_DRAW_GROUND_LINE:
            pg.draw.line(screen, (0, 0, 0),
                         (0, get_ground_y()), (WIDTH, get_ground_y()), 2)

        bird.update(key_lst, screen)
        enemies.update()
        enemies.draw(screen)

        if boss_active and boss:
            boss.update()
            if bird.rect.colliderect(boss.rect):
                if bird.get_vy() > 0 and bird.rect.bottom <= boss.rect.top + 20:
                    boss.on_hit()
            boss.draw(screen)

        pg.display.update()
        tmr += 1
        clock.tick(FPS)


if __name__ == "__main__":
    pg.init()
    main()
    pg.quit()
    sys.exit()
