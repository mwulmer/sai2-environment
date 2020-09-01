from sai2_environment.tasks.task import Task
import numpy as np

PUSH_HORIZONTAL = 0
PUSH_VERTICAL = 1
np.set_printoptions(precision=3, suppress=True)


class MoveObjectToTarget(Task):
    def __init__(self, task_name, redis_client, camera_handler, simulation=True):
        self._task_name = task_name
        self._client = redis_client
        self._simulation = simulation
        self.camera_handler = camera_handler
        self.traj = []
        self.cumulative_reward = 0
        self.TARGET_OBJ_POSITION_KEY = "sai2::ReinforcementLearning::move_object_to_target::object_position"
        self.GOAL_POSITION_KEY = "sai2::ReinforcementLearning::move_object_to_target::goal_position"
        self.CURRENT_POS_KEY = "sai2::ReinforcementLearning::current_position"
        self.DESIRED_POS_KEY = "sai2::ReinforcementLearning::desired_position"

        if simulation:
            self.goal_position = self._client.redis2array(
                self._client.get(self.GOAL_POSITION_KEY))
                        
            self.current_obj_position = self.get_puck_position()
            self.last_obj_position = self.current_obj_position
            self.total_distance = self.euclidean_distance(
            self.goal_position, self.current_obj_position)
        else:
            # setup the things that we need in the real world
            # self.goal_position = None
            # self.current_obj_position = None
            # self.last_obj_position = None

            # new modify
            self.current_obj_distance = self.camera_handler.grab_distance()
            self.last_obj_distance = self.current_obj_distance
            self.total_distance = self.camera_handler.grab_distance()

    def initialize_task(self):
        self.cumulative_reward = 0
        if self._simulation:
            self.goal_position = self._client.redis2array(
                self._client.get(self.GOAL_POSITION_KEY))
            self.current_obj_position = self.get_puck_position()
            self.last_obj_position = self.current_obj_position
            self.total_distance = self.euclidean_distance(
                self.goal_position, self.current_obj_position)-0.04
            self.traj = self.plan_optimal_trajectory()
        else:
            self.total_distance = self.camera_handler.grab_distance()
            self.traj = self.reset_trajectory()

    def compute_reward(self):
        """
        There is a total of 10 reward per episde. 
        1 for pushing the object to the goal and 9 for completing the task.
        Reward is normalized by the initial distance.
        """
        done = False
        reward = 0
        if self._simulation:
            self.last_obj_position = self.current_obj_position
            self.current_obj_position = self.get_puck_position()
            d0 = self.euclidean_distance(
                self.goal_position, self.last_obj_position) - 0.04
            d1 = self.euclidean_distance(
                self.goal_position, self.current_obj_position) - 0.04

            reward = (d0 - d1)/self.total_distance            
            done = self.is_in_goal(self.current_obj_position)
            
        else:
            # reward = 0
            # TODO
            # new modify
            self.last_obj_distance = self.current_obj_distance
            self.current_obj_distance = self.camera_handler.grab_distance()
            d_last = self.last_obj_distance
            d_current = self.current_obj_distance
            # When detecting no enough markers at the very beginning
            if d_current == 1:
                reward = 0
            else:
                reward = (d_last - d_current)/self.total_distance
                # reward = d_current
            
            done = d_current < 0.04
        
        self.cumulative_reward += reward
        if done:
            reward += 1 - self.cumulative_reward
            reward += 9
        return reward, done

    def act_optimally(self):
        # only works for the moving target action space right now
        desired_pos = self.get_desired_position()
        ee_pos = self.get_ee_position()
        action = np.array([0, 0, 0, 0, 0])
        if self.traj:
            required_behavior = self.traj[0]
            required_position = required_behavior[:3]
            required_stiffness = required_behavior[3:]
            if (self.euclidean_distance(required_position, ee_pos) > 0.03):
                action_pos = required_position - desired_pos[:3]
                #TODO add stiffness
                action = np.concatenate((action_pos, np.array([0,0])))
            else:
                self.traj.pop(0)
        return action

    def plan_optimal_trajectory(self):
        puck_pos = self.get_puck_position()

        # first action behind the
        a1 = np.array([puck_pos[0], puck_pos[1] +
                       np.sign(puck_pos[1])*0.1, 0.15, 50, 0])
        # go down z direction
        a2 = np.array([puck_pos[0], puck_pos[1] +
                       np.sign(puck_pos[1])*0.1, 0.05, 50, 0])
        # go to middle of the workspace
        a3 = np.array([puck_pos[0], np.sign(puck_pos[1])*0.05, 0.05, 0, 0])
        # go up again
        a4 = np.array([puck_pos[0], np.sign(puck_pos[1])*0.05, 0.18, 0, 0])
        # go behind puck again
        a5 = np.array([puck_pos[0]-0.10, 0, 0.18, 0, 0])
        # go down z again
        a6 = np.array([puck_pos[0]-0.10, 0, 0.05, 0, 0])
        # push towards goal in (0.6,0,0)
        a7 = np.array([0.65, 0, 0.05, 0, 0])
        trajectory = [a1, a2, a3, a4, a5, a6, a7]

        return trajectory

    def random_pose(self):
        
        obj_pos,marker0,marker1 = self.camera_handler.get_current_obj()

        e_y = marker0[1]- marker1[1]
        if (abs(e_y)>=0.02 and abs(e_y)<=0.07):
            x_new,y_new = self.x_y_mid_perpendicular(obj_pos,marker0,marker1)
            a_01 = np.array([x_new, y_new, 0.15, 50, 0])
            a_02 = np.array([x_new, y_new, 0.04, 50, 0])
            
            offset = np.random.uniform(0.5,1.2)
            # Move along the mid_perpendicular of marker0 and marker1
            a_03 = np.array([obj_pos[0]+offset*(obj_pos[0]-x_new),obj_pos[1]+offset*(obj_pos[1]-y_new), 0.04, 50, 0])
            a_04 = np.array([obj_pos[0]+offset*(obj_pos[0]-x_new),obj_pos[1]+offset*(obj_pos[1]-y_new), 0.15, 50, 0])
            trajectory = [a_01,a_02,a_03,a_04]
        else:
            trajectory = []
        self.traj = trajectory
    
    def reset_trajectory(self):

        obj_pos,marker0,marker1 = self.camera_handler.get_current_obj()
        marker3, marker4, marker5 = self.camera_handler.get_targetmarkers()
 
        if (np.sign(obj_pos[1])==np.sign(marker5[1])):
            pre_x = np.random.uniform(0.3,0.6)
            pre_y = np.random.uniform(-np.sign(marker5[1])*0.05,-np.sign(marker5[1])*0.2)
            pre_defined_pos = np.array([pre_x,pre_y,0,15]) 
            # Find obj and move the EE beside the obj
            a1 = np.array([obj_pos[0], obj_pos[1] + np.sign(obj_pos[1])*0.14, 0.15, 50, 0])
            # Go down 
            a2 = np.array([obj_pos[0], obj_pos[1] + np.sign(obj_pos[1])*0.14, 0.03, 50, 0])
            #Push along y axis
            a3 = np.array([obj_pos[0], pre_defined_pos[1], 0.03, 50, 0])
            #Up 
            a4 = np.array([obj_pos[0], pre_defined_pos[1], 0.15, 50, 0])
        else:
            #Set a predefined position for obj
            pre_x = np.random.uniform(0.3,0.6)   
            pre_defined_pos = np.array([pre_x,obj_pos[1],0,15])
            # Find obj and move the EE beside the obj
            if (obj_pos[0]<pre_x):
                a1 = np.array([obj_pos[0]-0.13, obj_pos[1], 0.15, 50, 0])
                # Go down 
                a2 = np.array([obj_pos[0]-0.13, obj_pos[1], 0.03, 50, 0])
                #Push along y axis
                a3 = np.array([pre_x, pre_defined_pos[1], 0.03, 50, 0])
                #Up 
                a4 = np.array([pre_x, pre_defined_pos[1], 0.15, 50, 0])
            else:
                a1 = np.array([obj_pos[0]+0.13, obj_pos[1], 0.15, 50, 0])
                # Go down 
                a2 = np.array([obj_pos[0]+0.13, obj_pos[1], 0.03, 50, 0])
                #Push along y axis
                a3 = np.array([pre_x, pre_defined_pos[1], 0.03, 50, 0])
                #Up 
                a4 = np.array([pre_x, pre_defined_pos[1], 0.15, 50, 0])

        
        trajectory = [a1, a2, a3, a4]
        print(trajectory)
        self.traj = trajectory

    def spilt_trajectory(self):
        
        obj_pos,marker0,marker1 = self.camera_handler.get_current_obj()
        marker3, marker4, marker5 = self.camera_handler.get_targetmarkers()
        dis_0 = self.euclidean_distance(marker0,marker5)
        dis_1 = self.euclidean_distance(marker1,marker5)
        if dis_0 <= dis_1:
            x_close = marker0[0]
            y_close = marker0[1]
            x_far = marker1[0]
            y_far = marker1[1]
        else:
            x_close = marker1[0]
            y_close = marker1[1]
            x_far = marker0[0]
            y_far = marker0[1]

        # Move to the closest marker to the goal along the line between marker0 and marker1 
        a_1 = np.array([2*x_close-x_far,2*y_close-y_far,0.15,50, 0])
        # Down
        a_2 = np.array([2*x_close-x_far,2*y_close-y_far,0.035,50, 0])
        # Move out the object along the line between marker0 and marker1 
        a_3 = np.array([1.7*x_far-0.7*x_close,1.7*y_far-0.7*y_close,0.035,50, 0])
        # Up
        a_4 = np.array([1.7*x_far-0.7*x_close,1.7*y_far-0.7*y_close,0.15,50, 0])
        trajectory = [a_1,a_2,a_3,a_4]
        self.traj = trajectory

    def is_reset(self):
        # ToDo :to get the
        if len(self.traj) == 0:
            return True
        return False
    
    def detector(self):
        print(self.current_obj_distance)
        obj_pos,marker0,marker1 = self.camera_handler.get_current_obj()
        marker3, marker4, marker5 = self.camera_handler.get_targetmarkers()
        if abs(marker0[1]-marker3[1])<0.05 or abs(marker0[1]-marker4[1])<0.05  or abs(marker1[1]-marker3[1])<0.05  or abs(marker1[1]-marker4[1])<0.05 :
            return True
        if self.current_obj_distance<0.06:
            return True
        return False
    
    def x_y_mid_perpendicular(self,mid,pos0,pos1):
        
        vec_ori = pos0-pos1
        vec_ori[2] = 0
        vec_x = np.array([1,0,0])
        vec_ori_norm =np.linalg.norm(vec_ori)
        product = vec_ori.dot(vec_x)
        theta = np.arccos(product/vec_ori_norm)

        if (theta>1.57):
            theta = 3.14-theta
        
        error_x = pos0[0]-pos1[0]
        error_y = pos0[1]-pos1[1]

        if ((error_x>0 and error_y>0) or (error_x<0 and error_y<0)) :
            x_new = mid[0] - 0.11*np.sin(theta)* np.sign(mid[1])
            y_new = mid[1] + 0.11*np.cos(theta)* np.sign(mid[1])
        else:
            x_new = mid[0] + 0.11*np.sin(theta)* np.sign(mid[1])
            y_new = mid[1] + 0.11*np.cos(theta)* np.sign(mid[1])

        return x_new,y_new

  
    def euclidean_distance(self, x1, x2):
        return np.linalg.norm(x1 - x2)

    def is_in_goal(self, pos):
        return (pos[0]-self.goal_position[0])**2 + (pos[1]-self.goal_position[1])**2 <= 0.04**2

    def get_ee_position(self):
        return self._client.redis2array(self._client.get(self.CURRENT_POS_KEY))

    def get_puck_position(self):
        return self._client.redis2array(self._client.get(self.TARGET_OBJ_POSITION_KEY))

    def get_desired_position(self):
        return self._client.redis2array(self._client.get(self.DESIRED_POS_KEY))
