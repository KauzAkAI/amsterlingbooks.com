# A.M. Sterling Books Website-

A cutting-edge author website featuring glassmorphic UI, video backgrounds, and immersive design.

## 📁 Folder Structure

```
amsterling-github/
├── index.html              # Main homepage
├── css/
│   └── styles.css          # All styles
├── js/
│   └── main.js             # All JavaScript
├── assets/
│   ├── images/             # Logos, author photo, etc.
│   │   ├── AM_Sterling_Logo_WHT.png
│   │   ├── AM_Sterling_Logo_BLK.png
│   │   └── favicon.png
│   ├── videos/             # Background video
│   │   └── space-battle.mp4
│   └── covers/             # Book covers
│       ├── sovereigns-war.jpg
│       ├── emissarys-gambit.jpg
│       └── ... (all book covers)
└── series/                 # Series subpages (to be created)
    ├── resonance-cycle.html
    ├── sovereign-protocol.html
    └── ...
```

## 🚀 Setup Instructions

### 1. Add Your Logo
Copy your logo files to `assets/images/`:
- `AM_Sterling_Logo_WHT.png` (white version for dark backgrounds)
- `AM_Sterling_Logo_BLK.png` (black version if needed)

### 2. Add a Background Video

Download a free space video from one of these sources:
- **Pixabay**: https://pixabay.com/videos/search/space/
- **Pexels**: https://www.pexels.com/search/videos/space/
- **Videezy**: https://www.videezy.com/free-video/space

**Recommended specs:**
- Resolution: 1920x1080 or 4K
- Duration: 15-30 seconds (should loop seamlessly)
- File size: Under 20MB for web performance
- Format: MP4 (H.264 codec)

Save the video as: `assets/videos/space-battle.mp4`

**Good search terms:**
- "space nebula loop"
- "space flight through stars"
- "galaxy flythrough"
- "spaceship fleet"
- "space battle"

### 3. Add Book Covers
Copy all your book cover images to `assets/covers/`:
- Use descriptive filenames (e.g., `sovereigns-war.jpg`, `signal-cover.png`)
- Update the `src` attributes in `index.html` to match your filenames

### 4. Deploy to GitHub Pages

1. Create a new repository on GitHub
2. Push this folder to the repository:
   ```bash
   git init
   git add .
   git commit -m "Initial website launch"
   git remote add origin https://github.com/YOUR_USERNAME/amsterling-website.git
   git push -u origin main
   ```
3. Go to repository Settings → Pages
4. Select "Deploy from a branch" → "main" → "/ (root)"
5. Your site will be live at: `https://YOUR_USERNAME.github.io/amsterling-website/`

**For custom domain (amsterlingbooks.com):**
1. Add a file called `CNAME` with your domain: `amsterlingbooks.com`
2. Configure your domain's DNS to point to GitHub Pages

## 🎨 Customization

### Colors
Edit the CSS variables in `css/styles.css`:
```css
:root {
    --magenta: #c41e8a;      /* Primary accent */
    --coral: #ff6b4a;        /* Secondary accent */
    --gold: #d4a853;         /* Highlight color */
    --cyan: #00d4ff;         /* Links/interactive */
}
```

### Fonts
The site uses Google Fonts:
- **Cinzel** - Display/headings (elegant, serif)
- **Rajdhani** - Body text (modern, readable)

To change fonts, update the Google Fonts link in `index.html` and the font variables in CSS.

### Adding New Pages
Copy the structure from `index.html` for consistent styling. The header, footer, and video background can be reused.

## 📱 Features

- ✅ Responsive design (mobile, tablet, desktop)
- ✅ Video background with fallback
- ✅ Glassmorphic UI panels
- ✅ Smooth scroll navigation
- ✅ Interactive portal cards with parallax
- ✅ 3D book hover effect
- ✅ Newsletter signup (needs backend integration)
- ✅ Mobile hamburger menu
- ✅ Scroll-triggered animations

## 🔧 Future Enhancements

- [ ] Individual series pages
- [ ] Book detail pages
- [ ] E-commerce integration
- [ ] Blog section
- [ ] Reading order interactive guide
- [ ] Character codex with images
- [ ] Newsletter integration (Mailchimp/ConvertKit)

## 📝 Notes

- The video background automatically pauses when the tab is hidden (performance)
- If autoplay is blocked, the video will start on first user interaction
- Mobile devices may not autoplay video; the CSS gradient fallback ensures the site still looks good

---

Built with 💜 by Claude for A.M. Sterling Books
