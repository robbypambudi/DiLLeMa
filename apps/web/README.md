## Setup Instructions

```bash
npm install
npm run dev
```

The application will be available at `http://localhost:3000`

### Production

```bash
npm run build
npm run preview
```

## Project Structure

```
src/
├── components/
│   ├── ui/
│   │   ├── Button.tsx
│   │   └── Input.tsx
│   ├── ChatDashboard.tsx
│   ├── ChatInput.tsx
│   ├── ChatWindow.tsx
│   ├── CollectionSelector.tsx
│   ├── ThemeToggle.tsx
│   └── WelcomePage.tsx
├── lib/
│   └── utils.ts
├── assets/
├── App.tsx
├── main.tsx
└── index.css
```

## State Management Strategy

The application uses **Zustand** for lightweight state management without requiring a backend database:

- **Session-based**: All data is stored in memory and cleared when the browser tab closes
- **Theme state**: Persisted across components using Zustand store
- **Chat history**: Maintained per session with message arrays
- **Collection selection**: Tracks currently selected collection for queries

## Key Features

- ✅ Clean, modern UI with dark/light mode toggle
- ✅ Welcome page with smooth onboarding flow
- ✅ Collection-based chat system
- ✅ Real-time streaming responses from FastAPI backend
- ✅ Session-based state management (no authentication required)
- ✅ Responsive design with Tailwind CSS
- ✅ TypeScript for type safety

## Integration with Backend

The frontend integrates with your existing FastAPI backend at `http://localhost:8000`:

- Fetches collections from `/api/v1/collection`
- Sends chat messages to `/api/v1/questions/stream`
- Handles streaming responses for real-time chat experience

## Dependencies

- **React 18** with TypeScript
- **Vite** for fast development and building
- **Tailwind CSS** for styling
- **Lucide React** for icons
- **Radix UI** for accessible components
