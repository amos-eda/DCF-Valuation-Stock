# GitHub Pages Deployment Guide

## Quick Setup

1. **Update your GitHub username** in `my-app/package.json`:
   - Replace `[YOUR_GITHUB_USERNAME]` with your actual GitHub username

2. **Install dependencies** (if not already done):
   ```bash
   cd my-app
   npm install
   ```

3. **Build and deploy manually** (optional):
   ```bash
   npm run deploy
   ```

## Automatic Deployment (Recommended)

The GitHub Actions workflow will automatically deploy your app when you push to the `main` branch.

## Manual Deployment Steps

1. **Build the project**:
   ```bash
   cd my-app
   npm run build
   ```

2. **Deploy to GitHub Pages**:
   ```bash
   npm run deploy
   ```

## GitHub Repository Settings

1. Go to your repository Settings
2. Navigate to "Pages" in the left sidebar
3. Set Source to "Deploy from a branch"
4. Select "gh-pages" branch and "/ (root)" folder
5. Click Save

## Troubleshooting

- **404 Error**: Make sure the `base` path in `vite.config.ts` matches your repository name
- **Build Failures**: Check the GitHub Actions tab for error details
- **Page Not Loading**: Verify the homepage URL in `package.json` matches your GitHub username

## Current Configuration

- **Base Path**: `/DCF-Valuation-Stock/` (matches repository name)
- **Build Output**: `dist/` folder
- **Deploy Branch**: `gh-pages`
- **GitHub Actions**: Automatic deployment on push to main
