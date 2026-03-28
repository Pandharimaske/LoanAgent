import React from "react";
import { Route, Routes, Navigate } from "react-router-dom";
import Home from "./component/Home";
import Signup from "./component/signup";
import Login from "./component/login";
import Dashboard from "./component/dashboard";

function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default App;
