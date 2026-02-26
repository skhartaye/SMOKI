import { useState, useEffect } from 'react';
import { ChevronRight, ChevronLeft, X } from 'lucide-react';
import '../styles/TutorialModal.css';

export default function TutorialModal({ triggerOnLogin = false }) {
  const [showTutorial, setShowTutorial] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    // Show tutorial on login (when triggerOnLogin is true)
    if (triggerOnLogin) {
      setShowTutorial(true);
      setCurrentStep(0);
    }
  }, [triggerOnLogin]);

  useEffect(() => {
    // Check if user has seen tutorial (per user basis) on initial mount
    if (!triggerOnLogin) {
      const username = localStorage.getItem('username');
      if (username) {
        const tutorialKey = `tutorialSeen_${username}`;
        const tutorialSeen = localStorage.getItem(tutorialKey);
        if (!tutorialSeen) {
          setShowTutorial(true);
        }
      }
    }
  }, [triggerOnLogin]);

  const tutorialSteps = [
    {
      title: '👋 Welcome to SMOKi',
      description: 'An intelligent emission monitoring system for vehicle surveillance. This tutorial will guide you through all features.',
      icon: '🚗'
    },
    {
      title: '📊 Dashboard',
      description: 'View real-time camera feed, top violators, and vehicle ranking. Monitor emission violations at a glance.',
      icon: '📈'
    },
    {
      title: '📋 Records',
      description: 'Access detailed sensor data logs with filtering by sensor type and date. Data is for indicative measurements only.',
      icon: '📝'
    },
    {
      title: '📈 Graphs',
      description: 'Visualize sensor trends over time with interactive charts. Filter by sensor type and date range.',
      icon: '📊'
    },
    {
      title: '🌡️ Sensors',
      description: 'Monitor real-time sensor readings including temperature, humidity, pressure, VOCs, NO₂, CO, and particulate matter.',
      icon: '🔬'
    },
    {
      title: '📧 Report Violator',
      description: 'Report vehicles with excessive emissions directly via email. Pre-filled with violation details.',
      icon: '⚠️'
    },
    {
      title: '⚠️ Sensor Status',
      description: 'Monitor ESP32 sensor connection status. Ribbon shows time since last data received in human-readable format.',
      icon: '🔌'
    },
    {
      title: '⚡ Key Features',
      description: 'Real-time WebRTC streaming, automatic smoke detection, emission violation tracking, and email reporting.',
      icon: '✨'
    },
    {
      title: '📌 Important Note',
      description: 'Air quality sensors are not reference grade. Data provided is for indicative measurements only and should be interpreted accordingly.',
      icon: '⚠️'
    },
    {
      title: '🎉 Ready to Go!',
      description: 'You\'re all set! Start monitoring emissions and protecting air quality. You can restart this tutorial anytime from settings.',
      icon: '🚀'
    }
  ];

  const handleNext = () => {
    if (currentStep < tutorialSteps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      closeTutorial();
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const closeTutorial = () => {
    const username = localStorage.getItem('username');
    if (username) {
      const tutorialKey = `tutorialSeen_${username}`;
      localStorage.setItem(tutorialKey, 'true');
    }
    setShowTutorial(false);
  };

  if (!showTutorial) {
    return null;
  }

  const step = tutorialSteps[currentStep];

  return (
    <div className="tutorial-overlay">
      <div className="tutorial-modal">
        <button 
          className="tutorial-close"
          onClick={closeTutorial}
          title="Close tutorial"
        >
          <X size={24} />
        </button>

        <div className="tutorial-header">
          <div className="tutorial-icon">{step.icon}</div>
          <h2>{step.title}</h2>
        </div>

        <div className="tutorial-content">
          <p>{step.description}</p>
        </div>

        <div className="tutorial-progress">
          <div className="progress-bar">
            <div 
              className="progress-fill"
              style={{ width: `${((currentStep + 1) / tutorialSteps.length) * 100}%` }}
            ></div>
          </div>
          <span className="progress-text">{currentStep + 1} / {tutorialSteps.length}</span>
        </div>

        <div className="tutorial-footer">
          <button 
            className="tutorial-btn tutorial-btn-secondary"
            onClick={closeTutorial}
          >
            Skip Tutorial
          </button>

          <div className="tutorial-nav">
            <button 
              className="tutorial-btn tutorial-btn-icon"
              onClick={handlePrev}
              disabled={currentStep === 0}
              title="Previous"
            >
              <ChevronLeft size={20} />
            </button>

            <button 
              className="tutorial-btn tutorial-btn-primary"
              onClick={handleNext}
            >
              {currentStep === tutorialSteps.length - 1 ? 'Finish' : 'Next'}
              <ChevronRight size={20} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
