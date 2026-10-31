# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Campos Ramos (Capitain Jack) and Sparky Stereo OS contributors.
"""The extension's words, in IngeTrazo's language when it has them here.

IngeTrazo's catalogue (``core.i18n``) is the application's own, so the
extension keeps its table: English as the source, Spanish (IngeTrazo's home
language) and the nine languages Sparky Stereo OS requires (en, pl, pt-BR,
fr, de, ja, ko, zh-CN, zh-TW).
"""
from __future__ import annotations

_TABLE = {
    "Stereo 3D": {
        "es": "Estéreo 3D", "pl": "Stereo 3D", "pt-BR": "Estéreo 3D",
        "fr": "Stéréo 3D", "de": "Stereo-3D", "ja": "ステレオ3D",
        "ko": "스테레오 3D", "zh-CN": "立体 3D", "zh-TW": "立體 3D"},
    "Enable 3D": {
        "es": "Activar 3D", "pl": "Włącz 3D", "pt-BR": "Ativar 3D",
        "fr": "Activer la 3D", "de": "3D aktivieren", "ja": "3Dを有効にする",
        "ko": "3D 사용", "zh-CN": "启用 3D", "zh-TW": "啟用 3D"},
    "Shows the model in stereo in a window of its own; the modelling stays in the main view.": {
        "es": "Muestra el modelo en estéreo en una ventana propia; el modelado sigue en la vista principal.",
        "pl": "Pokazuje model w stereo we własnym oknie; modelowanie pozostaje w widoku głównym.",
        "pt-BR": "Mostra o modelo em estéreo numa janela própria; a modelagem continua na vista principal.",
        "fr": "Affiche le modèle en stéréo dans sa propre fenêtre ; la modélisation reste dans la vue principale.",
        "de": "Zeigt das Modell stereoskopisch in einem eigenen Fenster; modelliert wird weiter in der Hauptansicht.",
        "ja": "モデルを専用のウィンドウにステレオで表示します。モデリングはメインビューのままです。",
        "ko": "모델을 별도의 창에 스테레오로 표시합니다. 모델링은 기본 보기에서 계속합니다.",
        "zh-CN": "在单独的窗口中以立体方式显示模型；建模仍在主视图中进行。",
        "zh-TW": "在獨立的視窗中以立體方式顯示模型；建模仍在主檢視中進行。"},
    "Render resolution per eye": {
        "es": "Resolución de render por ojo", "pl": "Rozdzielczość renderowania na oko",
        "pt-BR": "Resolução de renderização por olho", "fr": "Résolution de rendu par œil",
        "de": "Renderauflösung pro Auge", "ja": "片目あたりのレンダリング解像度",
        "ko": "한쪽 눈당 렌더링 해상도", "zh-CN": "每只眼睛的渲染分辨率",
        "zh-TW": "每隻眼睛的渲染解析度"},
    "How many pixels each eye is drawn with; the desktop resizes the eyes once, to the window.": {
        "es": "Cuántos píxeles tiene cada ojo al dibujarse; el escritorio redimensiona los ojos una sola vez, a la ventana.",
        "pl": "Ile pikseli ma każde oko; pulpit skaluje oczy raz, do rozmiaru okna.",
        "pt-BR": "Quantos pixels cada olho tem ao ser desenhado; a área de trabalho redimensiona os olhos uma única vez, para a janela.",
        "fr": "Le nombre de pixels de chaque œil ; le bureau redimensionne les yeux une seule fois, à la taille de la fenêtre.",
        "de": "Mit wie vielen Pixeln jedes Auge gezeichnet wird; der Desktop skaliert die Augen einmal, auf das Fenster.",
        "ja": "片目ごとに描画するピクセル数です。デスクトップがウィンドウに合わせて一度だけ拡大縮小します。",
        "ko": "각 눈을 그리는 픽셀 수입니다. 데스크톱이 창에 맞게 한 번만 크기를 조정합니다.",
        "zh-CN": "每只眼睛绘制的像素数；桌面只缩放一次，以适应窗口。",
        "zh-TW": "每隻眼睛繪製的像素數；桌面只縮放一次，以符合視窗。"},
    "Follow the window": {
        "es": "Seguir la ventana", "pl": "Według okna", "pt-BR": "Acompanhar a janela",
        "fr": "Suivre la fenêtre", "de": "Wie das Fenster", "ja": "ウィンドウに合わせる",
        "ko": "창 크기에 맞춤", "zh-CN": "跟随窗口", "zh-TW": "跟隨視窗"},
    "{lines}p (the width follows the window)": {
        "es": "{lines}p (el ancho sigue a la ventana)",
        "pl": "{lines}p (szerokość według okna)",
        "pt-BR": "{lines}p (a largura acompanha a janela)",
        "fr": "{lines}p (la largeur suit la fenêtre)",
        "de": "{lines}p (die Breite folgt dem Fenster)",
        "ja": "{lines}p（幅はウィンドウに合わせる）",
        "ko": "{lines}p (너비는 창에 맞춤)",
        "zh-CN": "{lines}p（宽度跟随窗口）",
        "zh-TW": "{lines}p（寬度跟隨視窗）"},
    "Display Settings…": {
        "es": "Configuración de pantalla…", "pl": "Ustawienia ekranu…",
        "pt-BR": "Configurações de tela…", "fr": "Paramètres d'affichage…",
        "de": "Anzeige-Einstellungen…", "ja": "ディスプレイ設定…",
        "ko": "디스플레이 설정…", "zh-CN": "显示设置…", "zh-TW": "顯示設定…"},
    "Opens the display settings, where each screen's 3D mode is chosen.": {
        "es": "Abre la configuración de pantalla, donde se elige el modo 3D de cada pantalla.",
        "pl": "Otwiera ustawienia ekranu, gdzie wybiera się tryb 3D każdego ekranu.",
        "pt-BR": "Abre as configurações de tela, onde se escolhe o modo 3D de cada tela.",
        "fr": "Ouvre les paramètres d'affichage, où se choisit le mode 3D de chaque écran.",
        "de": "Öffnet die Anzeige-Einstellungen, in denen der 3D-Modus jedes Bildschirms gewählt wird.",
        "ja": "ディスプレイ設定を開きます。各画面の3Dモードはそこで選びます。",
        "ko": "디스플레이 설정을 엽니다. 각 화면의 3D 모드는 여기에서 선택합니다.",
        "zh-CN": "打开显示设置，在那里为每个屏幕选择 3D 模式。",
        "zh-TW": "開啟顯示設定，在那裡為每個螢幕選擇 3D 模式。"},
    "Stereo view": {
        "es": "Vista estéreo", "pl": "Widok stereo", "pt-BR": "Vista estéreo",
        "fr": "Vue stéréo", "de": "Stereoansicht", "ja": "ステレオ表示",
        "ko": "스테레오 보기", "zh-CN": "立体视图", "zh-TW": "立體檢視"},
    "Stereo 3D is not available here: {reason}": {
        "es": "El estéreo 3D no está disponible aquí: {reason}",
        "pl": "Stereo 3D nie jest tu dostępne: {reason}",
        "pt-BR": "O estéreo 3D não está disponível aqui: {reason}",
        "fr": "La stéréo 3D n'est pas disponible ici : {reason}",
        "de": "Stereo-3D ist hier nicht verfügbar: {reason}",
        "ja": "ここではステレオ3Dを使用できません: {reason}",
        "ko": "여기에서는 스테레오 3D를 사용할 수 없습니다: {reason}",
        "zh-CN": "此处无法使用立体 3D：{reason}",
        "zh-TW": "此處無法使用立體 3D：{reason}"},
}

LANGUAGES = ("en", "es", "pl", "pt-BR", "fr", "de", "ja", "ko", "zh-CN", "zh-TW")


def language() -> str:
    try:
        from core.i18n import current_language
        return current_language() or "en"
    except Exception:                                   # noqa: BLE001
        return "en"


def tr(text: str, lang: str | None = None, **values) -> str:
    """``text`` in the current language (English when this table lacks it),
    with ``values`` filled in after the lookup."""
    lang = lang or language()
    out = _TABLE.get(text, {}).get(lang, text)
    return out.format(**values) if values else out
