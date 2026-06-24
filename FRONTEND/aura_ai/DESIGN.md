---
name: Aura AI
colors:
  surface: '#131315'
  surface-dim: '#131315'
  surface-bright: '#39393b'
  surface-container-lowest: '#0e0e10'
  surface-container-low: '#1b1b1d'
  surface-container: '#1f1f21'
  surface-container-high: '#2a2a2c'
  surface-container-highest: '#353437'
  on-surface: '#e4e2e4'
  on-surface-variant: '#c4c7c7'
  inverse-surface: '#e4e2e4'
  inverse-on-surface: '#303032'
  outline: '#8e9192'
  outline-variant: '#444748'
  surface-tint: '#c8c6c5'
  primary: '#c8c6c5'
  on-primary: '#313030'
  primary-container: '#121212'
  on-primary-container: '#7e7d7d'
  inverse-primary: '#5f5e5e'
  secondary: '#d4c5a9'
  on-secondary: '#382f1c'
  secondary-container: '#504630'
  on-secondary-container: '#c2b498'
  tertiary: '#c6c6c8'
  on-tertiary: '#2f3132'
  tertiary-container: '#101214'
  on-tertiary-container: '#7c7d7f'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e5e2e1'
  primary-fixed-dim: '#c8c6c5'
  on-primary-fixed: '#1c1b1b'
  on-primary-fixed-variant: '#474646'
  secondary-fixed: '#f1e1c4'
  secondary-fixed-dim: '#d4c5a9'
  on-secondary-fixed: '#221b09'
  on-secondary-fixed-variant: '#504630'
  tertiary-fixed: '#e2e2e4'
  tertiary-fixed-dim: '#c6c6c8'
  on-tertiary-fixed: '#1a1c1d'
  on-tertiary-fixed-variant: '#454749'
  background: '#131315'
  on-background: '#e4e2e4'
  surface-variant: '#353437'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 64px
    fontWeight: '600'
    lineHeight: 72px
    letterSpacing: 0.05em
  display-lg-mobile:
    fontFamily: Inter
    fontSize: 40px
    fontWeight: '600'
    lineHeight: 48px
    letterSpacing: 0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '500'
    lineHeight: 40px
    letterSpacing: 0.02em
  headline-sm:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 32px
    letterSpacing: 0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.1em
  label-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 8px
  gutter: 24px
  margin-desktop: 64px
  margin-mobile: 20px
  container-max: 1440px
---

## Brand & Style
The design system is engineered to evoke the atmosphere of a high-end architectural firm—precise, aspirational, and quietly powerful. It targets a premium demographic that values minimalist aesthetics and technological sophistication.

The visual direction merges **Modern Minimalism** with **Glassmorphism**. It utilizes expansive negative space to frame AI-generated renders as high-art. The interface should feel like a "Tesla-style" product reveal: dark, dramatic, and focusing on the interplay of light and shadow. Transitions must be fluid and eased, mimicking the motion of high-end camera pans across physical spaces.

## Colors
The palette is rooted in a "Nocturnal Luxury" theme.
- **Primary (Deep Charcoal):** Used for the core environment and deep background layers to create infinite depth.
- **Secondary (Champagne Gold):** Reserved for high-intent actions, premium badges, and delicate accents. This should be used sparingly to maintain its value.
- **Tertiary (Ambient White):** A soft, slightly blue-tinted white for primary typography and high-contrast iconography.
- **Neutral (Obsidian):** Used for surface-level containers, input fields, and borders.

The color mode is strictly dark-first to emphasize the "glow" of AI elements and interior lighting within renders.

## Typography
This design system utilizes **Inter** for its systematic clarity and modern architectural feel. 

Headlines utilize **generous tracking (0.02em to 0.05em)** to create an editorial, luxury feel. Larger display sizes should use a tighter weight (Medium) to maintain a sleek profile. Body text is kept clean with ample line height to ensure readability against dark, translucent backgrounds. Small labels and metadata should always use uppercase with tracking of 0.1em to differentiate technical data from narrative content.

## Layout & Spacing
The layout follows a **Fixed-Fluid hybrid grid**. Content is contained within a 1440px max-width container, centered on the viewport. 

On desktop, use a 12-column grid with 24px gutters. For the "Product Reveal" effect, utilize large asymmetrical margins (e.g., spanning 2 columns) to create a sense of curated space. Spacing follows an 8px linear scale. For AI "Stage" sections where renders are shown, use **viewport-height (VH)** based layouts to ensure the image remains the focal point regardless of screen aspect ratio.

## Elevation & Depth
Depth is created through **Ambient Layers** and **Glassmorphism**. 

1.  **The Void (Level 0):** The deep charcoal background (#121212).
2.  **Floating Panes (Level 1):** Surfaces use a background blur (20px-40px) with a 10% opacity white fill and a 1px "inner glow" border (white at 15% opacity).
3.  **Active Elements (Level 2):** Elements that are interactive use a soft, ultra-diffused shadow with a 40px blur, colored with a hint of the primary accent (#D4C5A9) at 5% opacity.

Avoid hard shadows. All depth is conveyed through light transmission and subtle border highlights that catch the "ambient light" of the interface.

## Shapes
The shape language is "Apple-style" geometric. A base radius of **0.5rem (8px)** is used for small components like inputs and chips. Larger containers and image cards use **1.5rem (24px)** to create a soft, premium feel that mimics high-end furniture design. Fully rounded pill shapes are reserved exclusively for tags and secondary buttons.

## Components
- **Primary Buttons:** High-contrast Champagne Gold background with dark text. No border, but an "outer glow" transition on hover.
- **Glass Chips:** Background-blurred pills with a 1px stroke. Used for AI style tags (e.g., "Mid-Century Modern").
- **Cards:** Borderless containers with a background blur. On hover, the 1px inner glow border increases in opacity from 10% to 30%.
- **Input Fields:** Bottom-aligned strokes only, or ultra-minimal dark fills. Focus state is indicated by a subtle gold glow on the bottom border.
- **The "Stage" Component:** A specialized full-screen component for AI renders with floating glass controls positioned at the bottom center.
- **Checkboxes/Radios:** Circular and minimalist. The selected state uses the Champagne Gold accent as a solid fill with no stroke.