import { Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import FaucetDashboard from "./pages/FaucetDashboard";
import Icehouse from "./pages/Icehouse";
import Analyst from "./pages/Analyst";
import Undercurrent from "./pages/Undercurrent";
import Weather from "./pages/Weather";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/faucet" element={<FaucetDashboard />} />
      <Route path="/icehouse" element={<Icehouse />} />
      <Route path="/analyst" element={<Analyst />} />
      <Route path="/undercurrent" element={<Undercurrent />} />
      <Route path="/weather" element={<Weather />} />
    </Routes>
  );
}
