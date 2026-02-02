# Shopify Price Manager - Web Interface

## Modern, Minimalistic Frontend

A clean, responsive web interface for managing all aspects of your Shopify price management system.

## Features

### 📊 Dashboard
- Real-time statistics (products, variants, mappings, pending plans)
- System configuration overview
- Quick action buttons
- Health status indicator

### 🛍️ Products
- Sync Shopify collections
- View all products with filtering
- Real-time sync status
- Product details modal

### 💰 Price Plans
- Generate new price plans
- View all plans with status badges
- Detailed plan inspection (items, prices, changes)
- One-click plan application
- Safety confirmations

### 📦 Booster Variants
- Generate variant split plans
- Track plan status
- Apply splits to Shopify
- View split history

### 📊 Booster Inventory
- Generate inventory adjustment plans
- Monitor inventory movements
- Apply inventory changes
- Track adjustments

### 🔗 Mappings
- View all SNKRDUNK to Shopify mappings
- Edit mapping status
- Add new mappings
- Manage translation cache

### 📈 Reports
- Generate stock reports
- View audit logs
- Filter by operation type
- Track all system operations

## Design Features

### Clean & Modern
- Minimalistic design
- Professional color scheme
- Smooth animations
- Responsive layout

### User Experience
- Tab-based navigation
- Real-time updates
- Loading indicators
- Success/error alerts
- Confirmation dialogs for destructive actions

### Mobile-Friendly
- Fully responsive design
- Touch-friendly buttons
- Optimized for all screen sizes

## Usage

### Starting the Server

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python run.py
```

### Accessing the Interface

Open your browser and navigate to:
```
http://localhost:8000
```

### Navigation

1. **Dashboard** - Overview and quick actions
2. **Products** - Sync and view products
3. **Price Plans** - Generate and apply pricing
4. **Booster Variants** - Split variants
5. **Booster Inventory** - Adjust inventory
6. **Mappings** - Manage product mappings
7. **Reports** - View logs and generate reports

## Workflow Examples

### Complete Price Update Workflow

1. **Sync Products**
   - Go to Products tab
   - Enter collection ID (e.g., 444175384827)
   - Click "Sync Collection"
   - Wait for confirmation

2. **Fetch SNKRDUNK Data**
   - Click "Fetch SNKRDUNK" on Dashboard
   - Wait for data to be cached

3. **Generate Price Plan**
   - Go to Price Plans tab
   - Configure options
   - Click "Generate Plan"
   - Review generated plan

4. **Review Plan**
   - Click "View" on the plan
   - Check price changes
   - Verify calculations

5. **Apply Plan**
   - Click "Apply" button
   - Confirm the action
   - Monitor progress

### Booster Variant Workflow

1. **Generate Split Plan**
   - Go to Booster Variants tab
   - Enter booster collection ID (444116140283)
   - Click "Generate Plan"

2. **Apply Variant Splits**
   - Review the plan
   - Click "Apply"
   - Confirm to split products into Box + Pack

### Inventory Management Workflow

1. **Generate Inventory Plan**
   - Go to Booster Inventory tab
   - Enter collection ID
   - Click "Generate Plan"

2. **Apply Inventory Changes**
   - Review adjustments
   - Click "Apply"
   - Confirm to move inventory from boxes to packs

## Technology Stack

- **Pure HTML5/CSS3/JavaScript** - No frameworks, fast and lightweight
- **Modern CSS** - CSS Grid, Flexbox, custom properties
- **Vanilla JS** - No dependencies, clean and maintainable
- **Fetch API** - Modern HTTP requests
- **Responsive Design** - Mobile-first approach

## Color Scheme

- Primary: #2563eb (Blue)
- Success: #10b981 (Green)
- Warning: #f59e0b (Amber)
- Danger: #ef4444 (Red)
- Neutral Grays: #f9fafb to #111827

## Browser Compatibility

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Customization

### Changing Colors

Edit `app/static/styles.css` and update the CSS variables:

```css
:root {
    --primary: #2563eb;
    --success: #10b981;
    /* ... etc */
}
```

### Adding New Tabs

1. Add tab button in `index.html`:
```html
<button class="tab" data-tab="my-tab">My Tab</button>
```

2. Add tab content:
```html
<div id="my-tab-tab" class="tab-content">
    <!-- Your content -->
</div>
```

3. Add load function in `app.js`:
```javascript
case 'my-tab': loadMyTab(); break;
```

## Tips

- Use the health indicator to monitor API status
- Check audit logs for troubleshooting
- Generate plans before applying (safety first!)
- Use the confirmation dialogs to prevent accidents
- Refresh tables after operations to see updates

## Screenshots

### Dashboard
Clean overview with stats and quick actions

### Products Table
View all synced products with filters and actions

### Price Plans
Generate, review, and apply price updates safely

### Responsive Design
Works perfectly on mobile and tablet devices

## Support

- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/v1/health
- Issues: Check audit logs in Reports tab
