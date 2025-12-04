const express = require('express');
const cors = require('cors');
const app = express();

app.use(cors());
app.use(express.json());

app.get('/', (req, res) => {
  res.json({
    success: true,
    message: '🚀 نجــم المحتــوى - TikTok عربي',
    status: '🟢 الخادم يعمل!',
    api: 'https://najem-backend.onrender.com'
  });
});

app.get('/api/videos', (req, res) => {
  res.json({
    success: true,
    videos: [
      {
        id: 1,
        videoUrl: "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
        user: "@نجم_المحتوى",
        caption: "أول فيديو على التطبيق! 🎉 #نجم_المحتوى",
        likes: 1250,
        comments: 89,
        shares: 45
      }
    ]
  });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`✅ الخادم يعمل: https://najem-backend.onrender.com`);
});
