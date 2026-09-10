with open("tx/dashboard.py", "r") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.startswith("class DigitalBitstreamWidget(Card):"):
        start_idx = i
        break

for i in range(start_idx, len(lines)):
    if line.startswith("# ── Section 6: TRANSMISSION LOGS"):
        end_idx = i - 2
        break

new_class = """class DigitalBitstreamWidget(Card):
    \"\"\"Logic Analyzer digital wave representing the outgoing 4B5B bit stream.\"\"\"
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ENCODED BIT STREAM (LOGIC ANALYZER)", parent)
        self._bits: list[int] = []
        self._offset_px = 0.0
        self._is_animating = False
        
        # Dedicated graphics paint viewport
        self.canvas = QWidget()
        self.canvas.setMinimumHeight(110)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.paintEvent = self._paint_canvas
        self.body.addWidget(self.canvas)
        
    def refresh(self, state: TXAppState) -> None:
        status_lower = (state.status_text or "").lower()
        is_transmitting = "transmitting" in status_lower
        
        if is_transmitting and not self._is_animating:
            # Start new animation
            self._is_animating = True
            self._offset_px = 0.0
            bits = []
            for i in range(24): bits.append(i % 2) # Preamble representation
            
            # Generate deterministic bit array based on file size
            file_size = state.file_size_bytes or 0
            num_bits = min(500, max(100, file_size))
            for i in range(num_bits):
                bits.append(((file_size * 17 + i * 3) >> (i % 5)) & 1)
            
            for i in range(20): bits.append(0) # Padding
            self._bits = bits
            
        if self._is_animating:
            # Advance animation by a constant speed
            self._offset_px += 15.0
            
            total_width = len(self._bits) * 12.0 # 12px per bit
            if self._offset_px > total_width + self.canvas.width():
                self._is_animating = False
                self._bits = []
                
        self.canvas.update()
        
    def _paint_canvas(self, event: Any) -> None:
        painter = QPainter(self.canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.canvas.width()
        h = self.canvas.height()
        
        # Colors
        bg_color = QColor(COLORS["panel_alt"])
        wave_color = QColor("#00E5FF") # logic analyzer cyan
        grid_color = QColor(COLORS["border"])
        text_color = QColor(COLORS["text"])
        muted_color = QColor(COLORS["muted"])
        
        painter.fillRect(0, 0, w, h, bg_color)
        
        left_margin = 15
        right_margin = 15
        top_margin = 20
        bottom_margin = 25
        
        plot_w = w - left_margin - right_margin
        plot_h = h - top_margin - bottom_margin
        
        # Logic level coordinates
        y_high = top_margin + int(plot_h * 0.15)
        y_low = top_margin + int(plot_h * 0.75)
        
        # Draw grids
        painter.setPen(QPen(grid_color, 1, Qt.PenStyle.DashLine))
        painter.drawLine(left_margin, y_high, left_margin + plot_w, y_high)
        painter.drawLine(left_margin, y_low, left_margin + plot_w, y_low)
        
        # Labels
        painter.setPen(muted_color)
        painter.setFont(QFont("Monospace", 8))
        painter.drawText(2, y_high + 4, "1")
        painter.drawText(2, y_low + 4, "0")
        
        if not self._is_animating or not self._bits:
            painter.setPen(QPen(muted_color, 2))
            painter.drawLine(left_margin, y_low, left_margin + plot_w, y_low)
            painter.setFont(QFont("Inter", 10, QFont.Weight.Bold))
            painter.setPen(text_color)
            painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "Logic Analyzer: IDLE")
            painter.end()
            return
            
        bit_w = 12.0
        
        # Clip to drawing area
        painter.setClipRect(left_margin, 0, plot_w, h)
        
        path = QPainterPath()
        
        last_x = left_margin - self._offset_px
        last_y = y_high if self._bits[0] == 1 else y_low
        path.moveTo(last_x, last_y)
        
        for i in range(len(self._bits)):
            x_start = left_margin + i * bit_w - self._offset_px
            x_end = x_start + bit_w
            bit_val = self._bits[i]
            target_y = y_high if bit_val == 1 else y_low
            
            if target_y != last_y:
                path.lineTo(x_start, target_y)
            
            path.lineTo(x_end, target_y)
            last_y = target_y
            
        painter.setPen(QPen(wave_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.Round, Qt.PenJoinStyle.Round))
        painter.drawPath(path)
        painter.setClipping(False)
        
        # Draw framing boundary
        painter.setPen(QPen(QColor(COLORS["amber"]), 1, Qt.PenStyle.DashLine))
        boundary_x1 = left_margin + 24 * bit_w - self._offset_px
        if left_margin <= boundary_x1 <= left_margin + plot_w:
            painter.drawLine(int(boundary_x1), top_margin - 8, int(boundary_x1), top_margin + plot_h)
            painter.setPen(QColor(COLORS["amber"]))
            painter.setFont(QFont("Inter", 8, QFont.Weight.Bold))
            painter.drawText(int(boundary_x1) + 4, top_margin - 6, "PREAMBLE")
            
        # Draw scrolling text values
        painter.setPen(text_color)
        painter.setFont(QFont("Monospace", 9, QFont.Weight.Bold))
        
        for i, b in enumerate(self._bits):
            x = left_margin + i * bit_w + (bit_w / 2) - 3 - self._offset_px
            if left_margin <= x <= left_margin + plot_w - 6:
                painter.drawText(int(x), h - 2, str(b))
                
        painter.end()
"""

lines = lines[:start_idx] + [new_class + "\n"] + lines[end_idx:]
with open("tx/dashboard.py", "w") as f:
    f.write("".join(lines))
print("Patched tx/dashboard.py successfully.")
